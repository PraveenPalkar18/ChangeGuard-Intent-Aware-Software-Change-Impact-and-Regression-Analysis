"""Repeatable Benchmark Evaluator for ChangeGuard Intent, Impact, and Test Selection (Milestone 10)."""
import json
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict

from backend.app.evaluation.benchmark_fixtures import get_benchmark_fixtures, BenchmarkFixture
from backend.app.analysis.service import ChangeGuardAnalysisService
from backend.app.github.models import PullRequestDetails, PRFileChange, PRCommit
from backend.app.intent.models import IntentClassification

logger = logging.getLogger("changeguard.evaluation")


@dataclass
class MetricScores:
    """Standard classification and retrieval metric triplet."""
    precision: float = 0.0
    recall: float = 0.0
    f1: float = 0.0
    support: int = 0


@dataclass
class IntentEvaluationResult:
    """Metrics breakdown for Intent Classification."""
    total_samples: int = 0
    accuracy: float = 0.0
    macro_precision: float = 0.0
    macro_recall: float = 0.0
    macro_f1: float = 0.0
    per_class_metrics: Dict[str, MetricScores] = field(default_factory=dict)
    confusion_matrix: Dict[str, Dict[str, int]] = field(default_factory=dict)
    false_positives: List[Dict[str, Any]] = field(default_factory=list)
    false_negatives: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class GraphImpactEvaluationResult:
    """Metrics breakdown for Impact and Dependency Identification."""
    total_expected_entities: int = 0
    total_predicted_entities: int = 0
    true_positives_count: int = 0
    precision: float = 0.0
    recall: float = 0.0
    f1: float = 0.0
    unresolved_blind_spots: int = 0


@dataclass
class TestSelectionEvaluationResult:
    """Metrics breakdown for Regression Test Selection."""
    total_expected_tests: int = 0
    total_selected_tests: int = 0
    relevant_tests_found: int = 0
    hit_rate_coverage: float = 0.0
    precision: float = 0.0


@dataclass
class ComprehensiveEvaluationReport:
    """Consolidated benchmark evaluation report across all ChangeGuard engines."""
    timestamp: str
    fixtures_evaluated: int
    provider_name: str
    intent_metrics: IntentEvaluationResult
    graph_metrics: GraphImpactEvaluationResult
    test_metrics: TestSelectionEvaluationResult
    risk_alignment_rate: float
    limitations: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class ChangeGuardEvaluator:
    """Executes repeatable evaluation against benchmark fixtures without external dependencies."""

    def __init__(self, fixtures: Optional[List[BenchmarkFixture]] = None):
        self.fixtures = fixtures if fixtures is not None else get_benchmark_fixtures()

    def run_evaluation(self, provider_name: str = "tfidf") -> ComprehensiveEvaluationReport:
        """Run all benchmark fixtures through ChangeGuard and calculate empirical metrics.

        Args:
            provider_name: AI model provider to evaluate ('tfidf', 'mock', etc.)

        Returns:
            ComprehensiveEvaluationReport with honest metrics, false positives, and limitations.
        """
        # Intent metrics tracking
        ground_truth_labels: List[str] = []
        predicted_labels: List[str] = []
        sample_meta: List[Dict[str, Any]] = []

        # Graph impact tracking
        all_expected_impacted = set()
        all_predicted_impacted = set()
        total_unknown_relationships = 0

        # Test selection tracking
        all_expected_tests = set()
        all_selected_tests = set()

        # Risk level tracking
        risk_matches = 0
        total_risk_evaluated = 0

        # Execute each fixture end-to-end
        for idx, fix in enumerate(self.fixtures, start=1):
            # Construct mock importer and client for this fixture
            pr_details = self._build_pr_details_from_fixture(fix, idx)
            mock_importer = self._create_fixture_importer(pr_details)
            mock_client = self._create_fixture_client(fix)

            service = ChangeGuardAnalysisService(
                importer=mock_importer,
                github_client=mock_client,
            )

            # Analyze PR
            report = service.analyze_pull_request(
                owner="benchmark",
                repo="suite",
                pr_number=idx,
                fetch_source_files=True,
                provider_name=provider_name,
            )

            # 1. Collect Intent Classifications per hunk
            for file_diff in fix.files:
                for hunk_fix in file_diff.hunks:
                    # Find corresponding predicted hunk
                    pred_class = None
                    for rep_file in report.files:
                        if rep_file.filename == file_diff.filename:
                            for rep_hunk in rep_file.hunks:
                                if rep_hunk.hunk_index == hunk_fix.hunk_index:
                                    pred_class = rep_hunk.classification.value
                                    break

                    if pred_class is None:
                        pred_class = "UNCERTAIN"

                    expected_class = hunk_fix.ground_truth_intent
                    ground_truth_labels.append(expected_class)
                    predicted_labels.append(pred_class)
                    sample_meta.append({
                        "fixture_id": fix.fixture_id,
                        "file": file_diff.filename,
                        "hunk_index": hunk_fix.hunk_index,
                        "expected": expected_class,
                        "predicted": pred_class,
                    })

            # 2. Collect Graph Impact Entities
            predicted_entity_names = set()
            if report.change_graph and report.change_graph.impacted_entities:
                for ent in report.change_graph.impacted_entities:
                    predicted_entity_names.add(ent.name)
            if report.risk_assessment:
                total_unknown_relationships += report.risk_assessment.unknown_relationships_count
                for ent in report.risk_assessment.entity_risks:
                    predicted_entity_names.add(ent.name)

            for exp_ent in fix.expected_impacted_entities:
                all_expected_impacted.add(f"{fix.fixture_id}::{exp_ent}")
            for pred_ent in predicted_entity_names:
                all_predicted_impacted.add(f"{fix.fixture_id}::{pred_ent}")

            # 3. Collect Test Selection
            selected_test_names = set()
            if report.test_selection and report.test_selection.recommended_tests:
                for t in report.test_selection.recommended_tests:
                    selected_test_names.add(t.test_id)

            for exp_test in fix.expected_selected_tests:
                all_expected_tests.add(f"{fix.fixture_id}::{exp_test}")
            for sel_test in selected_test_names:
                all_selected_tests.add(f"{fix.fixture_id}::{sel_test}")

            # 4. Collect Risk Level Alignment
            if report.risk_assessment:
                total_risk_evaluated += 1
                if report.risk_assessment.overall_risk_level.value == fix.expected_risk_level:
                    risk_matches += 1

        # Calculate Intent Metrics
        intent_res = self._compute_intent_metrics(ground_truth_labels, predicted_labels, sample_meta)

        # Calculate Graph Impact Metrics
        graph_res = self._compute_graph_metrics(
            all_expected_impacted, all_predicted_impacted, total_unknown_relationships
        )

        # Calculate Test Selection Metrics
        test_res = self._compute_test_metrics(all_expected_tests, all_selected_tests)

        risk_alignment = (risk_matches / total_risk_evaluated) if total_risk_evaluated > 0 else 0.0

        limitations = [
            "Evaluation was conducted on curated synthetic/real benchmark fixtures representing key architectural scenarios.",
            "Intent evaluation relies on TF-IDF textual/lexical semantic similarity and entity keyword matching.",
            "AST and dependency graph extraction is currently fully implemented for Python source files; other languages fall back to file-level tracking.",
            "Targeted regression test ranking does not execute candidate tests automatically, preserving local execution safety.",
            "Real-world generalization metrics require continuous sampling across production repository PR streams.",
        ]

        return ComprehensiveEvaluationReport(
            timestamp=datetime.now(timezone.utc).isoformat(),
            fixtures_evaluated=len(self.fixtures),
            provider_name=provider_name,
            intent_metrics=intent_res,
            graph_metrics=graph_res,
            test_metrics=test_res,
            risk_alignment_rate=round(risk_alignment, 4),
            limitations=limitations,
        )

    def _compute_intent_metrics(
        self,
        y_true: List[str],
        y_pred: List[str],
        meta: List[Dict[str, Any]],
    ) -> IntentEvaluationResult:
        classes = ["EXPLAINED", "UNEXPLAINED", "UNCERTAIN"]
        total = len(y_true)
        if total == 0:
            return IntentEvaluationResult()

        correct = sum(1 for yt, yp in zip(y_true, y_pred) if yt == yp)
        accuracy = correct / total

        # Initialize confusion matrix
        matrix: Dict[str, Dict[str, int]] = {c1: {c2: 0 for c2 in classes} for c1 in classes}
        for yt, yp in zip(y_true, y_pred):
            if yt in matrix and yp in matrix[yt]:
                matrix[yt][yp] += 1

        per_class: Dict[str, MetricScores] = {}
        precisions, recalls, f1s = [], [], []
        false_positives, false_negatives = [], []

        for c in classes:
            tp = matrix[c][c]
            fp = sum(matrix[other][c] for other in classes if other != c)
            fn = sum(matrix[c][other] for other in classes if other != c)
            support = sum(matrix[c].values())

            p = (tp / (tp + fp)) if (tp + fp) > 0 else 0.0
            r = (tp / (tp + fn)) if (tp + fn) > 0 else 0.0
            f1 = (2 * p * r / (p + r)) if (p + r) > 0 else 0.0

            per_class[c] = MetricScores(
                precision=round(p, 4),
                recall=round(r, 4),
                f1=round(f1, 4),
                support=support,
            )
            precisions.append(p)
            recalls.append(r)
            f1s.append(f1)

        for m in meta:
            if m["expected"] != m["predicted"]:
                if m["predicted"] == "EXPLAINED":
                    false_positives.append(m)
                else:
                    false_negatives.append(m)

        return IntentEvaluationResult(
            total_samples=total,
            accuracy=round(accuracy, 4),
            macro_precision=round(sum(precisions) / len(precisions), 4),
            macro_recall=round(sum(recalls) / len(recalls), 4),
            macro_f1=round(sum(f1s) / len(f1s), 4),
            per_class_metrics=per_class,
            confusion_matrix=matrix,
            false_positives=false_positives,
            false_negatives=false_negatives,
        )

    def _compute_graph_metrics(
        self,
        expected: set,
        predicted: set,
        unknown_count: int,
    ) -> GraphImpactEvaluationResult:
        tp = len(expected & predicted)
        fp = len(predicted - expected)
        fn = len(expected - predicted)

        p = (tp / len(predicted)) if predicted else 0.0
        r = (tp / len(expected)) if expected else 0.0
        f1 = (2 * p * r / (p + r)) if (p + r) > 0 else 0.0

        return GraphImpactEvaluationResult(
            total_expected_entities=len(expected),
            total_predicted_entities=len(predicted),
            true_positives_count=tp,
            precision=round(p, 4),
            recall=round(r, 4),
            f1=round(f1, 4),
            unresolved_blind_spots=unknown_count,
        )

    def _compute_test_metrics(
        self,
        expected: set,
        selected: set,
    ) -> TestSelectionEvaluationResult:
        tp = len(expected & selected)
        hit_rate = (tp / len(expected)) if expected else 0.0
        p = (tp / len(selected)) if selected else 0.0

        return TestSelectionEvaluationResult(
            total_expected_tests=len(expected),
            total_selected_tests=len(selected),
            relevant_tests_found=tp,
            hit_rate_coverage=round(hit_rate, 4),
            precision=round(p, 4),
        )

    def _build_pr_details_from_fixture(self, fix: BenchmarkFixture, pr_num: int) -> PullRequestDetails:
        files = []
        for f in fix.files:
            files.append(
                PRFileChange(
                    filename=f.filename,
                    status="modified",
                    patch=f.patch,
                    additions=f.patch.count("\n+"),
                    deletions=f.patch.count("\n-"),
                    changes=1,
                )
            )

        return PullRequestDetails(
            owner="benchmark",
            repo="suite",
            pr_number=pr_num,
            title=fix.title,
            description=fix.description,
            author=fix.author,
            state="open",
            created_at=datetime.now(timezone.utc).isoformat(),
            base_branch="main",
            head_branch="feature",
            commits_count=1,
            changed_files_count=len(files),
            total_additions=10,
            total_deletions=2,
            commits=[
                PRCommit(
                    sha=f"sha_{pr_num}",
                    message=f"{fix.title}\n\n{fix.description}",
                    author_name=fix.author,
                )
            ],
            files=files,
        )

    def _create_fixture_importer(self, pr_details: PullRequestDetails):
        class FixtureImporter:
            def import_pull_request(self, owner: str, repo: str, pr_number: int):
                return pr_details

        return FixtureImporter()

    def _create_fixture_client(self, fix: BenchmarkFixture):
        class FixtureClient:
            def get_file_content(self, owner: str, repo: str, path: str, ref: Optional[str] = None):
                # Normalize path separators
                norm_path = path.replace("\\", "/")
                return fix.repo_sources.get(norm_path)

        return FixtureClient()

    @staticmethod
    def generate_markdown_report(report: ComprehensiveEvaluationReport) -> str:
        """Render a publication-ready GitHub-flavored Markdown evaluation report."""
        im = report.intent_metrics
        gm = report.graph_metrics
        tm = report.test_metrics

        md = []
        md.append(f"# ChangeGuard — System Evaluation Report (Milestone 10)\n")
        md.append(f"**Generated:** `{report.timestamp}` | **Provider:** `{report.provider_name}` | **Fixtures Evaluated:** `{report.fixtures_evaluated}`\n")
        md.append("## 1. Executive Summary\n")
        md.append(
            f"ChangeGuard was evaluated using a repeatable benchmark suite comprising {report.fixtures_evaluated} "
            f"curated architectural pull request scenarios containing {im.total_samples} distinct diff hunks with "
            f"manually verified ground-truth labels for intent, AST dependency relationships, and regression test selection.\n"
        )
        md.append("| Engine / Capability | Metric | Value | Sample Size / Support |")
        md.append("| :--- | :--- | :--- | :--- |")
        md.append(f"| **Intent Classification** | Overall Accuracy | **{im.accuracy * 100:.1f}%** | {im.total_samples} hunks |")
        md.append(f"| **Intent Classification** | Macro F1-Score | **{im.macro_f1:.2f}** | {im.total_samples} hunks |")
        md.append(f"| **Dependency Impact** | Impacted Entity Recall | **{gm.recall * 100:.1f}%** | {gm.total_expected_entities} entities |")
        md.append(f"| **Dependency Impact** | Impacted Entity Precision | **{gm.precision * 100:.1f}%** | {gm.total_predicted_entities} entities |")
        md.append(f"| **Test Selection** | Target Test Coverage (Hit Rate) | **{tm.hit_rate_coverage * 100:.1f}%** | {tm.total_expected_tests} expected tests |")
        md.append(f"| **Risk Assessment** | Risk Tier Alignment | **{report.risk_alignment_rate * 100:.1f}%** | {report.fixtures_evaluated} PR scenarios |\n")

        md.append("## 2. Intent Classification Breakdown\n")
        md.append("| Intent Class | Precision | Recall | F1-Score | Ground Truth Support |")
        md.append("| :--- | :--- | :--- | :--- | :--- |")
        for cls_name, m in im.per_class_metrics.items():
            md.append(f"| `{cls_name}` | {m.precision:.2f} | {m.recall:.2f} | {m.f1:.2f} | {m.support} |")
        md.append("\n### Confusion Matrix\n")
        md.append("| Ground Truth \\ Predicted | EXPLAINED | UNEXPLAINED | UNCERTAIN |")
        md.append("| :--- | :--- | :--- | :--- |")
        for c1 in ["EXPLAINED", "UNEXPLAINED", "UNCERTAIN"]:
            row = [str(im.confusion_matrix.get(c1, {}).get(c2, 0)) for c2 in ["EXPLAINED", "UNEXPLAINED", "UNCERTAIN"]]
            md.append(f"| **{c1}** | " + " | ".join(row) + " |")

        if im.false_positives or im.false_negatives:
            md.append("\n### Discrepancy Analysis (False Positives / False Negatives)\n")
            for fp in im.false_positives:
                md.append(f"- **False Positive** in `{fp['fixture_id']}` ({fp['file']} hunk #{fp['hunk_index']}): Expected `{fp['expected']}`, but classified as `{fp['predicted']}`.")
            for fn in im.false_negatives:
                md.append(f"- **False Negative** in `{fn['fixture_id']}` ({fn['file']} hunk #{fn['hunk_index']}): Expected `{fn['expected']}`, but classified as `{fn['predicted']}`.")
        else:
            md.append("\n*Zero false positives or false negatives observed on the current benchmark suite.*\n")

        md.append("## 3. Dependency Graph & Impact Identification\n")
        md.append(f"- **Expected Impacted Entities:** {gm.total_expected_entities}")
        md.append(f"- **Predicted Impacted Entities:** {gm.total_predicted_entities}")
        md.append(f"- **True Positives:** {gm.true_positives_count}")
        md.append(f"- **Precision:** {gm.precision:.2f} | **Recall:** {gm.recall:.2f} | **F1-Score:** {gm.f1:.2f}")
        md.append(f"- **Unresolved External Import Blind Spots:** {gm.unresolved_blind_spots}\n")

        md.append("## 4. Regression Test Selection Usefulness\n")
        md.append(f"- **Expected Critical Tests:** {tm.total_expected_tests}")
        md.append(f"- **Selected Tests Recommended:** {tm.total_selected_tests}")
        md.append(f"- **Relevant Tests Identified:** {tm.relevant_tests_found}")
        md.append(f"- **Target Test Coverage (Hit Rate):** {tm.hit_rate_coverage * 100:.1f}%\n")

        md.append("## 5. Explicit System Limitations\n")
        for lim in report.limitations:
            md.append(f"- {lim}")

        return "\n".join(md)
