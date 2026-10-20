"""Tests for ChangeGuard Milestone 10 (Evaluation Runner and Benchmark Suite)."""
import os
import json
import pytest

from backend.app.evaluation.benchmark_fixtures import get_benchmark_fixtures
from backend.app.evaluation.evaluator import ChangeGuardEvaluator, ComprehensiveEvaluationReport


def test_benchmark_fixtures_integrity():
    """Verify that all benchmark fixtures have valid structures and required labels."""
    fixtures = get_benchmark_fixtures()
    assert len(fixtures) >= 4

    for fix in fixtures:
        assert fix.fixture_id.startswith("PR-")
        assert len(fix.files) > 0
        assert len(fix.repo_sources) > 0
        assert fix.expected_risk_level in ["LOW", "MEDIUM", "HIGH"]

        for f in fix.files:
            assert f.patch is not None
            assert len(f.hunks) > 0
            for h in f.hunks:
                assert h.ground_truth_intent in ["EXPLAINED", "UNEXPLAINED", "UNCERTAIN"]


def test_evaluator_run_and_metrics_calculation(tmp_path):
    """Verify that ChangeGuardEvaluator executes cleanly and computes empirical metrics."""
    evaluator = ChangeGuardEvaluator()
    report = evaluator.run_evaluation(provider_name="tfidf")

    assert isinstance(report, ComprehensiveEvaluationReport)
    assert report.fixtures_evaluated >= 4
    assert report.provider_name == "tfidf"

    # Intent metrics
    im = report.intent_metrics
    assert im.total_samples > 0
    assert 0.0 <= im.accuracy <= 1.0
    assert 0.0 <= im.macro_f1 <= 1.0
    assert "EXPLAINED" in im.per_class_metrics
    assert "UNEXPLAINED" in im.per_class_metrics
    assert "UNCERTAIN" in im.per_class_metrics
    assert im.confusion_matrix is not None

    # Graph metrics
    gm = report.graph_metrics
    assert gm.total_expected_entities > 0
    assert 0.0 <= gm.recall <= 1.0
    assert 0.0 <= gm.precision <= 1.0

    # Test selection metrics
    tm = report.test_metrics
    assert tm.total_expected_tests > 0
    assert 0.0 <= tm.hit_rate_coverage <= 1.0

    # Risk alignment
    assert 0.0 <= report.risk_alignment_rate <= 1.0

    # Report serialization
    report_dict = report.to_dict()
    assert isinstance(report_dict, dict)
    assert "intent_metrics" in report_dict

    # Markdown generation
    md = ChangeGuardEvaluator.generate_markdown_report(report)
    assert "# ChangeGuard" in md
    assert "Intent Classification" in md
    assert "Executive Summary" in md
