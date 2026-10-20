"""ChangeGuard On-Demand CLI Tool: Fetch, analyze, and inspect real GitHub Pull Requests."""
import os
import sys
import json
import argparse
from pathlib import Path
from datetime import datetime, timezone

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.app.core.config import settings
from backend.app.core.exceptions import ChangeGuardException
from backend.app.analysis.service import ChangeGuardAnalysisService
from backend.app.monitoring.state_store import MonitoringStateStore
from backend.app.monitoring.models import PRStateRecord, PRProcessingStatus


def print_section(title: str):
    print("\n" + "=" * 70)
    print(f" {title}")
    print("=" * 70)


def print_subsection(title: str):
    print("\n" + "-" * 70)
    print(f" {title}")
    print("-" * 70)


def main():
    parser = argparse.ArgumentParser(
        description="ChangeGuard CLI — Run end-to-end intent, impact, risk, and regression analysis on a GitHub PR."
    )
    parser.add_argument("--owner", required=True, help="GitHub repository owner or organization (e.g. 'pallets')")
    parser.add_argument("--repo", required=True, help="GitHub repository name (e.g. 'flask')")
    parser.add_argument("--pr", type=int, required=True, help="Pull Request number (e.g. 5000)")
    parser.add_argument(
        "--provider",
        default=settings.AI_PROVIDER,
        help=f"AI model provider ('tfidf', 'codebert', 'mock'. Default: '{settings.AI_PROVIDER}')",
    )
    parser.add_argument(
        "--no-source",
        action="store_true",
        help="Disable full repository source fetching (limits analysis to diff hunk line ranges)",
    )
    parser.add_argument("--json", action="store_true", help="Output full raw JSON report to stdout")

    args = parser.parse_args()

    print(f"[*] ChangeGuard: Connecting to GitHub repository '{args.owner}/{args.repo}'...")
    print(f"[*] Target: Pull Request #{args.pr} | Provider: {args.provider}")

    try:
        service = ChangeGuardAnalysisService()
        report = service.analyze_pull_request(
            owner=args.owner,
            repo=args.repo,
            pr_number=args.pr,
            fetch_source_files=not args.no_source,
            provider_name=args.provider,
        )

        # Automatically persist into local state store so dashboard can visualize it
        try:
            store = MonitoringStateStore()
            now_iso = datetime.now(timezone.utc).isoformat()
            rec = PRStateRecord(
                repo_key=f"{args.owner}/{args.repo}",
                pr_number=args.pr,
                head_sha=report.head_branch or "HEAD",
                title=report.title or "",
                author=report.author or "",
                status=PRProcessingStatus.COMPLETED,
                retry_count=0,
                created_at=now_iso,
                last_polled_at=now_iso,
                last_analyzed_at=now_iso,
                error_message=None,
                analysis_report=report,
            )
            store.save_pr_record(rec)
        except Exception:
            pass

        if args.json:
            print(json.dumps(report.model_dump(), indent=2, default=str))
            return

        # 1. Executive Summary
        print_section(f"CHANGEGUARD ANALYSIS REPORT: #{report.pr_number} — {report.title}")
        print(f"Repository   : {report.owner}/{report.repo}")
        print(f"Author       : @{report.author}")
        print(f"State        : {report.state.upper()}")
        print(f"Branches     : {report.base_branch} <- {report.head_branch}")
        print(f"AI Provider  : {report.ai_provider} ({report.ai_model})")
        print(f"Files / Hunks: {report.total_files_analyzed} files | {report.total_hunks_analyzed} hunks")

        # 2. Risk Assessment
        if report.risk_assessment:
            ra = report.risk_assessment
            print_subsection(f"RISK ASSESSMENT: [{ra.overall_risk_level.value}] (Score: {ra.overall_risk_score:.2f})")
            print(f"Summary: {ra.summary}")
            if ra.high_risk_reasons:
                print("\nHigh Risk Reasons:")
                for r in ra.high_risk_reasons:
                    print(f"  [!] {r}")
            if ra.primary_impact_paths:
                print("\nPrimary Propagation Impact Paths:")
                for p in ra.primary_impact_paths:
                    print(f"  --> {p.path_description} (Distance: {p.distance})")

        # 3. Intent Findings
        print_subsection("INTENT FINDINGS & HUNK CLASSIFICATION")
        print(f"Overall Intent: {report.overall_intent_summary}")
        print(f"Counts: {report.explained_count} Explained | {report.unexplained_count} Unexplained | {report.uncertain_count} Uncertain\n")

        for f in report.files:
            print(f"File: {f.filename} [{f.status.upper()}] (Entities in AST: {f.ast_entities_found})")
            for h in f.hunks:
                cls_tag = f"[{h.classification.value}]"
                print(f"  Hunk #{h.hunk_index} (Lines {h.old_start_line}->{h.new_start_line}) {cls_tag} (Conf: {h.confidence:.2f}, Sim: {h.similarity_score:.2f})")
                if h.matched_entity_name:
                    print(f"    Target Symbol : {h.matched_entity_name} ({h.matched_entity_type}) [{h.association_type}]")
                print(f"    Reason        : {h.reason}")
                if h.evidence:
                    for ev in h.evidence:
                        print(f"    Evidence      : {ev}")

        # 4. Dependency Graph & Blast Radius
        if report.change_graph:
            cg = report.change_graph
            print_subsection(f"CHANGE & DEPENDENCY GRAPH (Nodes: {cg.total_nodes}, Edges: {cg.total_edges})")
            print(f"Directly Changed Entities : {len(cg.changed_entities)}")
            print(f"Downstream Impacted Count : {cg.impacted_entities_count} entities in {cg.impacted_files_count} files")
            if cg.impacted_entities:
                print("Downstream Impacted Entities:")
                for ie in cg.impacted_entities[:8]:
                    print(f"  * {ie.name} ({ie.entity_type.value}) in {ie.file_path} (Distance: {ie.min_distance})")
                if len(cg.impacted_entities) > 8:
                    print(f"  ... and {len(cg.impacted_entities) - 8} more entities")

        # 5. Targeted Regression Test Selection
        if report.test_selection:
            ts = report.test_selection
            print_subsection(f"TARGETED REGRESSION TEST SELECTION ({ts.selected_tests_count} Recommended / {ts.total_tests_discovered} Discovered)")
            print(f"Summary: {ts.summary}")
            if ts.recommended_tests:
                print("\nRecommended Test Execution Plan:")
                for t in ts.recommended_tests:
                    print(f"  [{t.priority.value}] {t.test_id} (Score: {t.score:.2f}, Match: {t.match_type.value})")
                    print(f"      Command: {t.suggested_command}")
                    if t.evidence:
                        print(f"      Evidence: {t.evidence[0]}")
            else:
                print("  No targeted test candidates identified via static AST call sites or naming heuristics.")

        # 6. Limitations
        if report.processing_limitations:
            print_subsection("ANALYSIS LIMITATIONS & BOUNDARIES")
            for lim in report.processing_limitations:
                print(f"  * {lim}")

        print("\n" + "=" * 70)
        print(" [SUCCESS] Analysis complete. Saved to local persistent store.")
        print(" View full interactive visualization: http://localhost:8000/dashboard")
        print("=" * 70 + "\n")

    except ChangeGuardException as exc:
        print(f"\n[!] ChangeGuard Error: {exc.message}", file=sys.stderr)
        if exc.details:
            print(f"    Details: {json.dumps(exc.details, default=str)}", file=sys.stderr)
        sys.exit(1)
    except Exception as exc:
        print(f"\n[!] Unexpected Error: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
