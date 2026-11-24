"""Validation test suite for ChangeGuard Intent Analysis and Dependency Graph improvements.

Covers all 8 controlled test scenarios:
1. Aligned change
2. Unrelated hunk (scope creep)
3. Contradictory change
4. Uncertain / ambiguous intent
5. Harmless documentation-only change
6. Downstream caller and test regression selection
7. Dynamic / unresolved dependency handling
8. Multiple paths to same downstream entity (deduplication & count consistency)
Plus:
9. ShopFlow PR #1 regression case
10. Graceful fallback on LLM failure / unconfigured API
"""
import pytest
from backend.app.repository.tree_sitter_parser import TreeSitterPythonParser
from backend.app.preprocessing.diff_parser import parse_patch
from backend.app.intent.models import HunkContext, PRContext, IntentClassification, UncertaintyLevel
from backend.app.intent.semantic_engine import (
    DeterministicSemanticEngine,
    LLMSemanticEngine,
    SemanticCache,
    create_semantic_engine,
)
from backend.app.intent.intent_analyzer import IntentAnalyzer
from backend.app.intent.providers.tfidf_provider import TFIDFSimilarityProvider
from backend.app.graph.models import (
    NodeType,
    EdgeType,
    RelationshipCertainty,
    ChangeGraphReport,
)
from backend.app.graph.graph_builder import ChangeGraphBuilder
from backend.app.impact.risk_analyzer import RiskAnalyzer, RiskLevel
from backend.app.testing.selector import RegressionTestSelector, TestPriority


@pytest.fixture
def parser():
    return TreeSitterPythonParser()


@pytest.fixture
def deterministic_semantic_engine():
    return DeterministicSemanticEngine()


# -----------------------------------------------------------------------------
# Scenario 1: Clearly Aligned Change
# -----------------------------------------------------------------------------
def test_scenario_1_clearly_aligned_change(deterministic_semantic_engine):
    """PR description says normalize input; diff implements strip() and lower() normalization."""
    pr_ctx = PRContext(
        title="fix: normalize product names in input validation",
        description="Ensure product name inputs are stripped of whitespace and lowercased before saving.",
        changed_files=["app/validators.py"],
    )
    patch = """@@ -10,3 +10,4 @@
 def validate_product_name(name):
-    return name
+    if not name:
+        return ''
+    return name.strip().lower()
"""
    hunks = parse_patch(patch, filename="app/validators.py")
    assert len(hunks) == 1
    hunk = hunks[0]

    hunk_ctx = HunkContext(
        file_path="app/validators.py",
        hunk_index=1,
        hunk=hunk,
        association_type="function_body",
    )

    assessment = deterministic_semantic_engine.assess_hunk(pr_ctx, hunk_ctx, similarity_score=0.75)

    assert assessment.classification == IntentClassification.EXPLAINED
    assert "strip" in assessment.apparent_purpose.lower() or "lower" in assessment.apparent_purpose.lower() or "normaliz" in assessment.apparent_purpose.lower()
    assert assessment.uncertainty_level == UncertaintyLevel.LOW
    assert len(assessment.contradiction_signals) == 0


# -----------------------------------------------------------------------------
# Scenario 2: Unrelated Hunk Added (Scope Creep)
# -----------------------------------------------------------------------------
def test_scenario_2_unrelated_hunk_added(deterministic_semantic_engine):
    """PR title is about updating product validation, but hunk modifies billing discount rate."""
    pr_ctx = PRContext(
        title="fix: validate user email format",
        description="Add regex validation for email strings on registration.",
        changed_files=["app/validators.py", "app/billing.py"],
    )
    patch = """@@ -50,3 +50,3 @@
 def calculate_fee(amount):
-    return amount * 0.05
+    return amount * 0.01
"""
    hunks = parse_patch(patch, filename="app/billing.py")
    hunk = hunks[0]

    hunk_ctx = HunkContext(
        file_path="app/billing.py",
        hunk_index=1,
        hunk=hunk,
        association_type="function_body",
    )

    # Low similarity (0.10) between email validation and fee calculation
    assessment = deterministic_semantic_engine.assess_hunk(pr_ctx, hunk_ctx, similarity_score=0.10)

    assert assessment.classification == IntentClassification.UNEXPLAINED
    assert "fee" in assessment.apparent_purpose.lower() or "billing" in assessment.apparent_purpose.lower()
    assert len(assessment.missing_context) > 0


# -----------------------------------------------------------------------------
# Scenario 3: Contradictory Change
# -----------------------------------------------------------------------------
def test_scenario_3_contradictory_change(deterministic_semantic_engine):
    """PR states 'Add strict authentication and validation', but code removes authentication check."""
    pr_ctx = PRContext(
        title="feat: add strict authentication check",
        description="Verify user token before allowing access to order processing.",
        changed_files=["app/auth.py"],
    )
    patch = """@@ -20,4 +20,3 @@
 def verify_access(token):
-    if not token or token == 'guest':
-        raise PermissionError('Unauthorized')
+    # disable authentication check
+    return True
"""
    hunks = parse_patch(patch, filename="app/auth.py")
    hunk = hunks[0]

    hunk_ctx = HunkContext(
        file_path="app/auth.py",
        hunk_index=1,
        hunk=hunk,
        association_type="function_body",
    )

    assessment = deterministic_semantic_engine.assess_hunk(pr_ctx, hunk_ctx, similarity_score=0.45)

    assert assessment.classification == IntentClassification.CONTRADICTORY
    assert len(assessment.contradiction_signals) > 0
    assert any("removes validation" in s.lower() or "disable" in s.lower() or "unconditional" in s.lower() for s in assessment.contradiction_signals)


# -----------------------------------------------------------------------------
# Scenario 4: Vague / Uncertain Intent
# -----------------------------------------------------------------------------
def test_scenario_4_uncertain_intent(deterministic_semantic_engine):
    """PR title is ambiguous ('misc fixes') without explanation."""
    pr_ctx = PRContext(
        title="misc fixes",
        description="",
        changed_files=["app/helpers.py"],
    )
    patch = """@@ -1,2 +1,3 @@
 def helper():
+    flag = 42
     return flag
"""
    hunks = parse_patch(patch, filename="app/helpers.py")
    hunk = hunks[0]

    hunk_ctx = HunkContext(
        file_path="app/helpers.py",
        hunk_index=1,
        hunk=hunk,
        association_type="function_body",
    )

    assessment = deterministic_semantic_engine.assess_hunk(pr_ctx, hunk_ctx, similarity_score=0.25)

    assert assessment.classification == IntentClassification.UNCERTAIN
    assert assessment.uncertainty_level in (UncertaintyLevel.MEDIUM, UncertaintyLevel.HIGH)
    assert any("vague" in m.lower() or "description" in m.lower() for m in assessment.missing_context)


# -----------------------------------------------------------------------------
# Scenario 5: Harmless Documentation-Only Change
# -----------------------------------------------------------------------------
def test_scenario_5_harmless_doc_change(deterministic_semantic_engine):
    """PR updates documentation and comments; confirmed harmless with low blast radius."""
    pr_ctx = PRContext(
        title="docs: update API documentation",
        description="Clarify docstring formatting and API usage examples.",
        changed_files=["app/service.py"],
    )
    patch = """@@ -1,5 +1,6 @@
 \"\"\"Service module.\"\"\"
-# old comment
+# updated comment explaining arguments
+# see docs/api.md for details
"""
    hunks = parse_patch(patch, filename="app/service.py")
    hunk = hunks[0]

    hunk_ctx = HunkContext(
        file_path="app/service.py",
        hunk_index=1,
        hunk=hunk,
        association_type="comment",
    )

    assessment = deterministic_semantic_engine.assess_hunk(pr_ctx, hunk_ctx, similarity_score=0.60)

    assert assessment.classification == IntentClassification.EXPLAINED
    assert "doc" in assessment.apparent_purpose.lower() or "comment" in assessment.apparent_purpose.lower()
    assert assessment.uncertainty_level == UncertaintyLevel.LOW


# -----------------------------------------------------------------------------
# Scenario 6: Downstream Caller & Regression Test Selection
# -----------------------------------------------------------------------------
def test_scenario_6_downstream_caller_and_test_selection(parser):
    """A change in a core function impacts callers and selects corresponding regression test."""
    service_code = """def calculate_total(price, tax):
    return price + (price * tax)
"""
    checkout_code = """from app.service import calculate_total

def checkout_order(cart):
    total = calculate_total(cart.price, 0.1)
    return total
"""
    test_code = """from app.service import calculate_total

def test_calculate_total():
    assert calculate_total(100, 0.1) == 110
"""
    builder = ChangeGraphBuilder()
    builder.build_from_parse_results({
        "app/service.py": parser.parse_source("app/service.py", service_code),
        "app/checkout.py": parser.parse_source("app/checkout.py", checkout_code),
        "tests/test_service.py": parser.parse_source("tests/test_service.py", test_code),
    })

    # Core function is changed
    report = builder.compute_impact(["app/service.py::calculate_total"])

    # 1. Downstream entities: checkout_order in app/checkout.py AND test_calculate_total in tests/test_service.py
    impacted_names = [e.name for e in report.impacted_entities]
    assert "checkout_order" in impacted_names
    assert "test_calculate_total" in impacted_names
    assert "app/checkout.py" in report.impacted_files

    # 2. Test selector verification
    selector = RegressionTestSelector()
    test_selection = selector.select_tests(
        change_graph_report=report,
        test_parse_results={"tests/test_service.py": parser.parse_source("tests/test_service.py", test_code)},
    )
    assert test_selection.selected_tests_count >= 1
    selected_names = [t.test_name for t in test_selection.recommended_tests]
    assert "test_calculate_total" in selected_names
    assert test_selection.recommended_tests[0].priority == TestPriority.P0_CRITICAL


# -----------------------------------------------------------------------------
# Scenario 7: Dynamic or Unresolved Dependency Handling
# -----------------------------------------------------------------------------
def test_scenario_7_unresolved_dependency(parser):
    """Unresolved imports and missing source files do not crash; marked as UNKNOWN with limitations."""
    code = """from app.missing_submodule import unknown_function

def run_job():
    return unknown_function()
"""
    builder = ChangeGraphBuilder()
    builder.build_from_parse_results({
        "app/job.py": parser.parse_source("app/job.py", code),
    })

    # Graph should contain limitations for the unresolved internal import
    assert any("Unresolved repository import" in lim for lim in builder._limitations)

    report = builder.compute_impact(["app/job.py::run_job"])
    assert report.total_nodes >= 2
    assert any("missing_submodule" in lim for lim in report.graph_limitations)


# -----------------------------------------------------------------------------
# Scenario 8: Multiple Graph Paths to Same Downstream Entity (Deduplication)
# -----------------------------------------------------------------------------
def test_scenario_8_multiple_paths_diamond_dependency(parser):
    """Diamond graph: A is called by B and C; both B and C are called by D.
    D should be counted ONCE in impacted_entities, with duplicate paths excluded."""
    a_code = "def a(): return 'a'\n"
    b_code = "from app.a import a\ndef b(): return a()\n"
    c_code = "from app.a import a\ndef c(): return a()\n"
    d_code = "from app.b import b\nfrom app.c import c\ndef d(): return b() + c()\n"

    builder = ChangeGraphBuilder()
    builder.build_from_parse_results({
        "app/a.py": parser.parse_source("app/a.py", a_code),
        "app/b.py": parser.parse_source("app/b.py", b_code),
        "app/c.py": parser.parse_source("app/c.py", c_code),
        "app/d.py": parser.parse_source("app/d.py", d_code),
    })

    # 'a' is modified
    report = builder.compute_impact(["app/a.py::a"])

    # Unique entity verification
    impacted_node_ids = [e.node_id for e in report.impacted_entities]
    assert len(impacted_node_ids) == len(set(impacted_node_ids)), "Impacted entities must be unique!"

    # D must be in impacted entities
    d_entity = next((e for e in report.impacted_entities if e.name == "d"), None)
    assert d_entity is not None
    assert d_entity.min_distance == 2

    # Verify count consistency
    assert report.impacted_entities_count == len(report.impacted_entities)
    assert (
        report.direct_impacted_entities_count + report.transitive_impacted_entities_count
        == report.impacted_entities_count
    )
    assert (
        report.direct_impacted_files_count + report.transitive_impacted_files_count
        == report.impacted_files_count
    )


# -----------------------------------------------------------------------------
# Scenario 9: ShopFlow PR #1 Regression Case
# -----------------------------------------------------------------------------
def test_scenario_9_shopflow_pr1_regression(parser):
    """Simulate ShopFlow PR #1: 'fix: normalize product names in input validation'.
    Validates hunk classification, dependency edges, and test selection."""
    validator_code = """import re

def normalize_product_name(name: str) -> str:
    if not name:
        return ""
    cleaned = re.sub(r'\\s+', ' ', name.strip())
    return cleaned.lower()

def validate_product_input(payload: dict) -> bool:
    if "name" not in payload:
        return False
    payload["name"] = normalize_product_name(payload["name"])
    return len(payload["name"]) > 0
"""
    api_code = """from app.validators import validate_product_input

def create_product_endpoint(data):
    if not validate_product_input(data):
        raise ValueError("Invalid product")
    return {"status": "created", "name": data["name"]}
"""
    test_code = """from app.validators import normalize_product_name, validate_product_input

def test_normalize_product_name():
    assert normalize_product_name("  Cool   SHIRT  ") == "cool shirt"

def test_validate_product_input():
    data = {"name": "  Shoes  "}
    assert validate_product_input(data) is True
    assert data["name"] == "shoes"
"""
    builder = ChangeGraphBuilder()
    builder.build_from_parse_results({
        "app/validators.py": parser.parse_source("app/validators.py", validator_code),
        "app/api.py": parser.parse_source("app/api.py", api_code),
        "tests/test_validators.py": parser.parse_source("tests/test_validators.py", test_code),
    })

    # Suppose normalize_product_name was changed in PR #1
    report = builder.compute_impact(["app/validators.py::normalize_product_name"])

    # Downstream impacts: validate_product_input (calling normalize_product_name)
    impacted_names = {e.name for e in report.impacted_entities}
    assert "validate_product_input" in impacted_names
    assert "create_product_endpoint" in impacted_names  # Transitive caller

    # Direct vs Transitive counts
    assert report.direct_impacted_entities_count >= 1
    assert report.transitive_impacted_entities_count >= 1

    # Tests selected
    selector = RegressionTestSelector()
    test_selection = selector.select_tests(
        change_graph_report=report,
        test_parse_results={"tests/test_validators.py": parser.parse_source("tests/test_validators.py", test_code)},
    )
    assert any(t.test_name == "test_normalize_product_name" for t in test_selection.recommended_tests)


# -----------------------------------------------------------------------------
# Scenario 10: Graceful Fallback & Semantic Caching
# -----------------------------------------------------------------------------
def test_scenario_10_fallback_and_semantic_cache():
    """Verify that unconfigured LLM engine cleanly falls back to deterministic analysis,
    and semantic cache returns cached result on identical inputs."""
    cache = SemanticCache()
    assert cache._enabled is True

    # 1. Caching
    pr_ctx = PRContext(title="fix bug", description="fix null ptr", changed_files=["a.py"])
    patch = """@@ -1,1 +1,1 @@
-return None
+return x or 0
"""
    hunks = parse_patch(patch, filename="a.py")
    hunk = hunks[0]
    hunk_ctx = HunkContext(file_path="a.py", hunk_index=1, hunk=hunk)

    engine = DeterministicSemanticEngine()
    first_res = engine.assess_hunk(pr_ctx, hunk_ctx, 0.8)
    cache.set(pr_ctx, hunk_ctx, "deterministic", "deterministic-rule-v1", first_res)

    cached_res = cache.get(pr_ctx, hunk_ctx, "deterministic", "deterministic-rule-v1")
    assert cached_res is not None
    assert cached_res.classification == first_res.classification

    # Cache miss on different provider/model
    assert cache.get(pr_ctx, hunk_ctx, "other_provider", "other_model") is None

    # 2. LLMSemanticEngine without API key falls back to Deterministic without pretending to be LLM
    llm_engine = LLMSemanticEngine(api_key="")
    fallback_res = llm_engine.assess_hunk(pr_ctx, hunk_ctx, 0.8)
    assert fallback_res.classification == IntentClassification.EXPLAINED
    assert any("Deterministic" in m or "unavailable" in m for m in fallback_res.missing_context)
