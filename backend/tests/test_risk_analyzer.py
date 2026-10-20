"""Unit and integration tests for Impact Analysis and Risk Ranking (Milestone 6)."""
import pytest
from backend.app.repository.tree_sitter_parser import TreeSitterPythonParser
from backend.app.graph.graph_builder import ChangeGraphBuilder
from backend.app.graph.models import ChangeGraphReport, ImpactPath, ImpactedEntity, NodeType
from backend.app.analysis.models import FileAnalysisReport, HunkAnalysisDetail
from backend.app.intent.models import IntentClassification
from backend.app.github.models import PullRequestDetails, PRFileChange, PRCommit
from backend.app.impact.models import (
    RiskLevel,
    RelationshipConfidence,
    RiskFactor,
    EntityRiskDetail,
    FileRiskDetail,
    PRRiskAssessment,
)
from backend.app.impact.risk_analyzer import RiskAnalyzer


@pytest.fixture
def parser():
    return TreeSitterPythonParser()


@pytest.fixture
def risk_analyzer():
    return RiskAnalyzer()


def test_low_risk_scenario(parser, risk_analyzer):
    """Test localized change with zero downstream callers and explained intent is rated LOW risk."""
    source = """def format_currency(amount):
    return f"${amount:.2f}"
"""
    parse_res = parser.parse_source("app/utils.py", source)
    builder = ChangeGraphBuilder()
    builder.build_from_parse_results({"app/utils.py": parse_res})

    # Changed entity has zero callers in repo
    graph_report = builder.compute_impact(["app/utils.py::format_currency"])

    file_report = FileAnalysisReport(
        filename="app/utils.py",
        status="modified",
        hunks_count=1,
        hunks=[
            HunkAnalysisDetail(
                hunk_index=1,
                header="@@ -1,2 +1,2 @@",
                old_start_line=1,
                new_start_line=1,
                change_type="modified",
                matched_entity_id="app/utils.py::format_currency",
                matched_entity_name="format_currency",
                matched_entity_type="function",
                classification=IntentClassification.EXPLAINED,
                confidence=0.9,
                similarity_score=0.85,
                reason="Aligned with PR intent",
                model_used="tfidf",
                provider_used="tfidf",
            )
        ],
    )

    assessment = risk_analyzer.analyze_risk(
        change_graph_report=graph_report,
        graph=builder.graph,
        file_reports=[file_report],
    )

    assert assessment.overall_risk_level == RiskLevel.LOW
    assert assessment.overall_risk_score <= 0.35
    assert len(assessment.high_risk_reasons) == 0
    assert "LOW RISK" in assessment.summary

    # Verify per-file risk
    assert len(assessment.file_risks) == 1
    assert assessment.file_risks[0].risk_level == RiskLevel.LOW

    # Verify per-entity risk
    assert len(assessment.entity_risks) >= 1
    assert assessment.entity_risks[0].risk_level == RiskLevel.LOW
    assert assessment.entity_risks[0].dependent_entities_count == 0


def test_medium_risk_scenario(parser, risk_analyzer):
    """Test moderate change affecting 1-2 direct callers is rated MEDIUM risk."""
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

    graph_report = builder.compute_impact(["app/billing.py::calculate_discount"])

    file_report = FileAnalysisReport(
        filename="app/billing.py",
        status="modified",
        hunks_count=1,
        hunks=[
            HunkAnalysisDetail(
                hunk_index=1,
                header="@@ -1,2 +1,3 @@",
                old_start_line=1,
                new_start_line=1,
                change_type="modified",
                matched_entity_id="app/billing.py::calculate_discount",
                matched_entity_name="calculate_discount",
                matched_entity_type="function",
                classification=IntentClassification.EXPLAINED,
                confidence=0.8,
                similarity_score=0.7,
                reason="Aligned with PR intent",
                model_used="tfidf",
                provider_used="tfidf",
            )
        ],
    )

    assessment = risk_analyzer.analyze_risk(
        change_graph_report=graph_report,
        graph=builder.graph,
        file_reports=[file_report],
    )

    assert assessment.overall_risk_level == RiskLevel.MEDIUM
    assert 0.30 <= assessment.overall_risk_score < 0.70
    assert "MEDIUM RISK" in assessment.summary
    assert assessment.confirmed_relationships_count >= 1

    # Check impacted entity relationship type
    process_order_risk = next(e for e in assessment.entity_risks if e.name == "process_order")
    assert process_order_risk.relationship_type == RelationshipConfidence.CONFIRMED_STATIC
    assert process_order_risk.min_distance == 1


def test_high_risk_blast_radius_scenario(parser, risk_analyzer):
    """Test high blast radius (>4 downstream entities across multiple files/depth) triggers HIGH risk with impact paths."""
    core_src = """def authenticate_user(token):
    return token == "valid"
"""
    api1_src = """from app.core import authenticate_user
def login_route(token):
    return authenticate_user(token)
"""
    api2_src = """from app.core import authenticate_user
def admin_route(token):
    return authenticate_user(token)
"""
    api3_src = """from app.api2 import admin_route
def root_admin_action(token):
    return admin_route(token)
"""
    api4_src = """from app.core import authenticate_user
def api_gateway(token):
    return authenticate_user(token)
"""
    builder = ChangeGraphBuilder()
    builder.build_from_parse_results({
        "app/core.py": parser.parse_source("app/core.py", core_src),
        "app/api1.py": parser.parse_source("app/api1.py", api1_src),
        "app/api2.py": parser.parse_source("app/api2.py", api2_src),
        "app/api3.py": parser.parse_source("app/api3.py", api3_src),
        "app/api4.py": parser.parse_source("app/api4.py", api4_src),
    })

    graph_report = builder.compute_impact(["app/core.py::authenticate_user"], max_depth=5)

    file_report = FileAnalysisReport(
        filename="app/core.py",
        status="modified",
        hunks_count=2,
        hunks=[
            HunkAnalysisDetail(
                hunk_index=1,
                header="@@ -1,2 +1,4 @@",
                old_start_line=1,
                new_start_line=1,
                change_type="modified",
                matched_entity_id="app/core.py::authenticate_user",
                matched_entity_name="authenticate_user",
                matched_entity_type="function",
                classification=IntentClassification.EXPLAINED,
                confidence=0.8,
                similarity_score=0.7,
                reason="Refactor auth",
                model_used="tfidf",
                provider_used="tfidf",
            )
        ],
    )

    assessment = risk_analyzer.analyze_risk(
        change_graph_report=graph_report,
        graph=builder.graph,
        file_reports=[file_report],
    )

    assert assessment.overall_risk_level == RiskLevel.HIGH
    assert assessment.overall_risk_score >= 0.70
    assert len(assessment.high_risk_reasons) > 0
    assert any("blast radius" in r.lower() or "entities" in r.lower() for r in assessment.high_risk_reasons)

    # Must provide explainable supporting impact paths
    assert len(assessment.primary_impact_paths) > 0
    path_descs = [p.path_description for p in assessment.primary_impact_paths]
    assert any("authenticate_user" in d for d in path_descs)


def test_high_risk_unexplained_changes_with_downstream_impact(parser, risk_analyzer):
    """Test unexplained change with downstream callers triggers HIGH risk."""
    billing_src = """def calculate_discount(price, rate):
    return price * (1 - rate)
"""
    checkout_src = """from app.billing import calculate_discount
def process_order(price, rate):
    return calculate_discount(price, rate)
"""
    builder = ChangeGraphBuilder()
    builder.build_from_parse_results({
        "app/billing.py": parser.parse_source("app/billing.py", billing_src),
        "app/checkout.py": parser.parse_source("app/checkout.py", checkout_src),
    })

    graph_report = builder.compute_impact(["app/billing.py::calculate_discount"])

    file_report = FileAnalysisReport(
        filename="app/billing.py",
        status="modified",
        hunks_count=1,
        hunks=[
            HunkAnalysisDetail(
                hunk_index=1,
                header="@@ -1,2 +1,3 @@",
                old_start_line=1,
                new_start_line=1,
                change_type="modified",
                matched_entity_id="app/billing.py::calculate_discount",
                matched_entity_name="calculate_discount",
                matched_entity_type="function",
                classification=IntentClassification.UNEXPLAINED,
                confidence=0.88,
                similarity_score=0.12,
                reason="Completely unaligned change in billing logic",
                model_used="tfidf",
                provider_used="tfidf",
            )
        ],
    )

    assessment = risk_analyzer.analyze_risk(
        change_graph_report=graph_report,
        graph=builder.graph,
        file_reports=[file_report],
    )

    assert assessment.overall_risk_level == RiskLevel.HIGH
    assert assessment.overall_risk_score >= 0.70
    assert any("unexplained" in r.lower() for r in assessment.high_risk_reasons)


def test_low_similarity_alone_does_not_label_high_risk(parser, risk_analyzer):
    """Requirement 6: Verify low similarity score on isolated leaf entity does NOT label PR as HIGH risk."""
    source = """def internal_format_date(ts):
    return str(ts)
"""
    parse_res = parser.parse_source("app/date_utils.py", source)
    builder = ChangeGraphBuilder()
    builder.build_from_parse_results({"app/date_utils.py": parse_res})

    # Leaf function with 0 callers
    graph_report = builder.compute_impact(["app/date_utils.py::internal_format_date"])

    file_report = FileAnalysisReport(
        filename="app/date_utils.py",
        status="modified",
        hunks_count=1,
        hunks=[
            HunkAnalysisDetail(
                hunk_index=1,
                header="@@ -1,2 +1,2 @@",
                old_start_line=1,
                new_start_line=1,
                change_type="modified",
                matched_entity_id="app/date_utils.py::internal_format_date",
                matched_entity_name="internal_format_date",
                matched_entity_type="function",
                classification=IntentClassification.UNEXPLAINED,  # Low similarity divergence
                confidence=0.7,
                similarity_score=0.08,  # Very low similarity
                reason="Low semantic similarity with PR title",
                model_used="tfidf",
                provider_used="tfidf",
            )
        ],
    )

    assessment = risk_analyzer.analyze_risk(
        change_graph_report=graph_report,
        graph=builder.graph,
        file_reports=[file_report],
    )

    # Must NOT be labeled HIGH solely because similarity score is low on a leaf function!
    assert assessment.overall_risk_level != RiskLevel.HIGH
    assert assessment.overall_risk_level in (RiskLevel.LOW, RiskLevel.MEDIUM)


def test_cycle_safety_during_risk_analysis(parser, risk_analyzer):
    """Test recursive cycles in dependency graph do not loop infinitely and compute valid risk."""
    source = """def ping(n):
    if n > 0:
        return pong(n - 1)
    return 0

def pong(n):
    if n > 0:
        return ping(n - 1)
    return 1
"""
    parse_res = parser.parse_source("app/recursive.py", source)
    builder = ChangeGraphBuilder()
    builder.build_from_parse_results({"app/recursive.py": parse_res})

    graph_report = builder.compute_impact(["app/recursive.py::ping"], max_depth=5)

    assessment = risk_analyzer.analyze_risk(
        change_graph_report=graph_report,
        graph=builder.graph,
        file_reports=[],
    )

    assert assessment.overall_risk_level in (RiskLevel.LOW, RiskLevel.MEDIUM)
    assert len(assessment.entity_risks) >= 2


def test_incomplete_graph_and_missing_source_handling(parser, risk_analyzer):
    """Test that missing source files and unresolved internal imports elevate uncertainty."""
    builder = ChangeGraphBuilder()
    builder.build_from_parse_results({
        "README.md": None,
        "app/unparsed.py": None,
    })

    graph_report = builder.compute_impact(["file:app/unparsed.py"])
    # Simulate an unresolved internal repository import
    graph_report.graph_limitations.append("Unresolved repository import 'app.internal.vault' in 'app/unparsed.py:10'")

    assessment = risk_analyzer.analyze_risk(
        change_graph_report=graph_report,
        graph=builder.graph,
        file_reports=[],
    )

    assert assessment.unknown_relationships_count >= 1
    assert any("blind spots" in f.description.lower() or "limitation" in f.name.lower() for f in assessment.risk_factors)


def test_relationship_confidence_distinction(parser, risk_analyzer):
    """Test that distance 1 is CONFIRMED_STATIC, distance 2 is POTENTIAL, and unparsed is UNKNOWN."""
    a_src = "def a(): return 1"
    b_src = "from app.a import a\ndef b(): return a()"
    c_src = "from app.b import b\ndef c(): return b()"

    builder = ChangeGraphBuilder()
    builder.build_from_parse_results({
        "app/a.py": parser.parse_source("app/a.py", a_src),
        "app/b.py": parser.parse_source("app/b.py", b_src),
        "app/c.py": parser.parse_source("app/c.py", c_src),
    })

    graph_report = builder.compute_impact(["app/a.py::a"], max_depth=5)

    assessment = risk_analyzer.analyze_risk(
        change_graph_report=graph_report,
        graph=builder.graph,
        file_reports=[],
    )

    b_risk = next(e for e in assessment.entity_risks if e.name == "b")
    c_risk = next(e for e in assessment.entity_risks if e.name == "c")

    # b is direct caller at distance 1
    assert b_risk.min_distance == 1
    assert b_risk.relationship_type == RelationshipConfidence.CONFIRMED_STATIC

    # c is indirect caller at distance 2
    assert c_risk.min_distance == 2
    assert c_risk.relationship_type == RelationshipConfidence.POTENTIAL
