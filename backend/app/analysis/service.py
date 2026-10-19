"""End-to-End ChangeGuard Analysis Service orchestrating M1-M4 pipelines."""
from typing import List, Optional, Dict
from backend.app.github.client import GitHubClient
from backend.app.github.importer import GitHubPRImporter
from backend.app.preprocessing.diff_parser import parse_patch
from backend.app.repository.tree_sitter_parser import TreeSitterPythonParser
from backend.app.repository.entity_mapper import EntityHunkMapper
from backend.app.repository.models import ParseResult
from backend.app.intent.intent_analyzer import IntentAnalyzer
from backend.app.intent.models import (
    PRContext,
    HunkContext,
    IntentClassification,
)
from backend.app.analysis.models import (
    PRAnalysisReport,
    FileAnalysisReport,
    HunkAnalysisDetail,
)
from backend.app.graph.graph_builder import ChangeGraphBuilder
from backend.app.graph.models import ChangeGraphReport


class ChangeGuardAnalysisService:
    """Orchestrates ingestion, diff parsing, AST code parsing, entity mapping, and intent analysis."""

    def __init__(
        self,
        importer: Optional[GitHubPRImporter] = None,
        github_client: Optional[GitHubClient] = None,
        intent_analyzer: Optional[IntentAnalyzer] = None,
        code_parser: Optional[TreeSitterPythonParser] = None,
        graph_builder: Optional[ChangeGraphBuilder] = None,
    ):
        self._importer = importer or GitHubPRImporter()
        self._github_client = github_client or GitHubClient()
        self._custom_intent_analyzer = intent_analyzer
        self._code_parser = code_parser or TreeSitterPythonParser()
        self._custom_graph_builder = graph_builder


    def analyze_pull_request(
        self,
        owner: str,
        repo: str,
        pr_number: int,
        fetch_source_files: bool = True,
        provider_name: Optional[str] = None,
    ) -> PRAnalysisReport:
        """Run complete end-to-end analysis on a GitHub Pull Request.

        Args:
            owner: GitHub repository owner.
            repo: GitHub repository name.
            pr_number: Pull request number.
            fetch_source_files: If True, fetches full repository source for Tree-sitter AST parsing.
            provider_name: Optional AI provider override ('tfidf', 'codebert', 'mock').

        Returns:
            PRAnalysisReport with per-file, per-hunk classifications, evidence, and limitations.
        """
        # Resolve active IntentAnalyzer based on explicit provider_name or injected instance
        if provider_name:
            active_analyzer = IntentAnalyzer(provider_name=provider_name)
        elif self._custom_intent_analyzer is not None:
            active_analyzer = self._custom_intent_analyzer
        else:
            active_analyzer = IntentAnalyzer()

        # 1. Ingest PR metadata, commits, and diff patches
        pr_details = self._importer.import_pull_request(owner=owner, repo=repo, pr_number=pr_number)

        # 2. Build Stated PR Intent Context
        commit_msgs = [c.message for c in pr_details.commits if c.message]
        pr_context = PRContext(
            pr_title=pr_details.title,
            pr_description=pr_details.description or "",
            commit_messages=commit_msgs,
        )

        global_limitations: List[str] = [
            "Semantic similarity alone does not constitute mathematical proof of intent alignment.",
            "Static analysis cannot detect dynamic runtime or indirect call linkages.",
        ]

        file_reports: List[FileAnalysisReport] = []
        total_hunks_analyzed = 0
        explained_count = 0
        unexplained_count = 0
        uncertain_count = 0

        # Change & Dependency Graph inputs (Milestone 5)
        parsed_files_map: Dict[str, Optional[ParseResult]] = {}
        file_statuses: Dict[str, str] = {}
        changed_entity_ids: List[str] = []

        # 3. Process each changed file
        for f in pr_details.files:
            file_limitations: List[str] = []
            file_statuses[f.filename] = f.status

            # Check if patch is available
            if not f.patch or not f.patch.strip():
                parsed_files_map[f.filename] = None
                file_reports.append(
                    FileAnalysisReport(
                        filename=f.filename,
                        status=f.status,
                        patch_available=False,
                        source_available=False,
                        ast_entities_found=0,
                        hunks_count=0,
                        hunks=[],
                        limitations=["No unified diff patch available (e.g. binary or unmodified file)."],
                    )
                )
                continue

            # Parse unified diff into structured hunks
            hunks = parse_patch(f.patch, filename=f.filename)

            # 4. Source-Aware AST Parsing where full source is available
            new_parse_result: Optional[ParseResult] = None
            old_parse_result: Optional[ParseResult] = None
            source_available = False

            is_python_file = f.filename.endswith(".py")

            if fetch_source_files and is_python_file:
                # Attempt to fetch new source at head SHA/branch
                ref_head = pr_details.head_sha or pr_details.head_branch
                new_source = self._github_client.get_file_content(owner, repo, f.filename, ref=ref_head)
                if new_source is not None:
                    new_parse_result = self._code_parser.parse_source(f.filename, new_source)
                    source_available = True

                # Attempt to fetch old source at base SHA/branch (for deleted line tracking)
                ref_base = pr_details.base_sha or pr_details.base_branch
                old_filename = f.previous_filename or f.filename
                old_source = self._github_client.get_file_content(owner, repo, old_filename, ref=ref_base)
                if old_source is not None:
                    old_parse_result = self._code_parser.parse_source(old_filename, old_source)
            elif not is_python_file:
                file_limitations.append("Non-Python source file; AST entity extraction skipped.")
            else:
                file_limitations.append("Full source fetching disabled; AST entity extraction skipped.")

            if is_python_file and not source_available and fetch_source_files:
                file_limitations.append("Full repository source could not be retrieved from GitHub API; entity mapping limited to diff hunk line ranges.")

            parsed_files_map[f.filename] = new_parse_result
            ast_entities_count = len(new_parse_result.entities) if (new_parse_result and new_parse_result.entities) else 0

            # 5. Process each hunk with Entity Mapping and Intent Analysis
            hunk_details: List[HunkAnalysisDetail] = []
            for hunk in hunks:
                # Map hunk lines to code entities
                associations = EntityHunkMapper.map_hunk_to_entities(
                    hunk=hunk,
                    file_path=f.filename,
                    new_parse_result=new_parse_result,
                    old_parse_result=old_parse_result,
                )

                # Identify primary matched entity if any
                primary_assoc = associations[0] if associations else None
                matched_id = primary_assoc.matched_entity_id if primary_assoc else None
                matched_name = primary_assoc.matched_entity_name if primary_assoc else None
                matched_type = primary_assoc.matched_entity_type.value if (primary_assoc and primary_assoc.matched_entity_type) else None
                assoc_type = primary_assoc.association_type if primary_assoc else "file_level"

                # Track changed entities for ChangeGraph (Milestone 5)
                if matched_id:
                    changed_entity_ids.append(matched_id)
                else:
                    changed_entity_ids.append(f.filename)


                # Find entity object for context if matched
                matched_entity_obj = None
                if matched_id and new_parse_result:
                    for ent in new_parse_result.entities:
                        if ent.id == matched_id:
                            matched_entity_obj = ent
                            break

                # 6. Intent Analysis
                hunk_ctx = HunkContext(
                    file_path=f.filename,
                    hunk_index=hunk.hunk_index,
                    hunk=hunk,
                    enclosing_entity=matched_entity_obj,
                    association_type=assoc_type,
                )

                intent_res = active_analyzer.analyze_hunk(pr_context, hunk_ctx)

                # Tally statistics
                if intent_res.classification == IntentClassification.EXPLAINED:
                    explained_count += 1
                elif intent_res.classification == IntentClassification.UNEXPLAINED:
                    unexplained_count += 1
                else:
                    uncertain_count += 1
                total_hunks_analyzed += 1

                # Construct hunk detail
                hunk_details.append(
                    HunkAnalysisDetail(
                        hunk_index=hunk.hunk_index,
                        header=hunk.header,
                        old_start_line=hunk.old_start_line,
                        new_start_line=hunk.new_start_line,
                        change_type=primary_assoc.change_type if primary_assoc else "modified",
                        matched_entity_id=matched_id,
                        matched_entity_name=matched_name,
                        matched_entity_type=matched_type,
                        association_type=assoc_type,
                        classification=intent_res.classification,
                        confidence=intent_res.confidence,
                        similarity_score=intent_res.similarity_score,
                        reason=intent_res.reason,
                        evidence=intent_res.evidence,
                        limitations=intent_res.limitations,
                        model_used=intent_res.model_used,
                        provider_used=intent_res.provider_used,
                    )
                )

            file_reports.append(
                FileAnalysisReport(
                    filename=f.filename,
                    status=f.status,
                    patch_available=True,
                    source_available=source_available,
                    ast_entities_found=ast_entities_count,
                    hunks_count=len(hunks),
                    hunks=hunk_details,
                    limitations=file_limitations,
                )
            )

        # 7. Construct overall summary
        if total_hunks_analyzed == 0:
            summary = "No diff hunks available to analyze in this Pull Request."
        elif unexplained_count == 0 and uncertain_count == 0:
            summary = f"All {total_hunks_analyzed} hunks are explained by the stated PR intent."
        elif unexplained_count > 0:
            summary = (
                f"Attention: {unexplained_count} of {total_hunks_analyzed} hunks contain changes that do not "
                f"align with the stated PR intent and warrant reviewer inspection."
            )
        else:
            summary = (
                f"{explained_count} of {total_hunks_analyzed} hunks explained; {uncertain_count} hunks have ambiguous "
                f"or cross-component overlap requiring reviewer verification."
            )

        provider_info = active_analyzer.provider.get_model_info()

        # 8. Build Change and Dependency Graph (Milestone 5)
        graph_builder = self._custom_graph_builder or ChangeGraphBuilder()
        graph_builder.build_from_parse_results(parsed_files_map, file_statuses)
        change_graph_report = graph_builder.compute_impact(changed_entity_ids)

        return PRAnalysisReport(
            owner=owner,
            repo=repo,
            pr_number=pr_number,
            title=pr_details.title,
            description=pr_details.description,
            author=pr_details.author,
            state=pr_details.state,
            base_branch=pr_details.base_branch,
            head_branch=pr_details.head_branch,
            ai_provider=active_analyzer.provider.provider_name,
            ai_model=active_analyzer.provider.model_name,
            total_files_analyzed=len(file_reports),
            total_hunks_analyzed=total_hunks_analyzed,
            explained_count=explained_count,
            unexplained_count=unexplained_count,
            uncertain_count=uncertain_count,
            overall_intent_summary=summary,
            files=file_reports,
            change_graph=change_graph_report,
            processing_limitations=global_limitations,
        )
