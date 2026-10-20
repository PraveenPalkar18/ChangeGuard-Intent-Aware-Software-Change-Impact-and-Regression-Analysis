"""Risk Analysis and Impact Ranking Engine (Milestone 6)."""
from __future__ import annotations
import logging
from typing import List, Dict, Any, Optional, Set, TYPE_CHECKING
import networkx as nx

from backend.app.graph.models import (
    NodeType,
    ImpactPath,
    ImpactedEntity,
    ChangeGraphReport,
)
if TYPE_CHECKING:
    from backend.app.analysis.models import FileAnalysisReport
from backend.app.github.models import PullRequestDetails
from backend.app.intent.models import IntentClassification
from backend.app.impact.models import (
    RiskLevel,
    RelationshipConfidence,
    RiskFactor,
    EntityRiskDetail,
    FileRiskDetail,
    PRRiskAssessment,
)

logger = logging.getLogger("changeguard.impact")


class RiskAnalyzer:
    """Evaluates explainable risk ranking based on graph impact, change scope, and intent alignment."""

    def analyze_risk(
        self,
        change_graph_report: ChangeGraphReport,
        graph: Optional[nx.DiGraph] = None,
        file_reports: Optional[List[FileAnalysisReport]] = None,
        pr_details: Optional[PullRequestDetails] = None,
    ) -> PRRiskAssessment:
        """Run comprehensive multi-factor risk assessment.

        Args:
            change_graph_report: Output from ChangeGraphBuilder.compute_impact.
            graph: Optional NetworkX directed graph from ChangeGraphBuilder.
            file_reports: Optional list of per-file analysis reports with diff hunks.
            pr_details: Optional PR metadata (title, body, lines changed).

        Returns:
            PRRiskAssessment containing overall risk, per-file risks, and per-entity risk rankings.
        """
        file_reports = file_reports or []
        limitations: List[str] = [
            "Static dependency analysis reflects AST call sites and explicit imports; dynamic runtime dispatch, reflection, or monkey-patching cannot be statically confirmed.",
            "Risk scores are heuristic indicators based on structural blast radius, change scope, and intent alignment; they do not represent calibrated probability of production regression.",
        ]

        # 1. Index hunk and file metrics
        file_metrics = self._extract_file_metrics(file_reports, pr_details)

        # 2. Evaluate Entity Risks (both directly changed and downstream impacted)
        entity_risks, primary_impact_paths = self._evaluate_entities(
            change_graph_report=change_graph_report,
            graph=graph,
            file_metrics=file_metrics,
        )

        # 3. Evaluate File Risks
        file_risks = self._evaluate_files(
            file_reports=file_reports,
            file_metrics=file_metrics,
            entity_risks=entity_risks,
            change_graph_report=change_graph_report,
        )

        # 4. Count relationship verification categories
        confirmed_count = 0
        potential_count = 0
        unknown_count = 0

        for ent in entity_risks:
            if ent.relationship_type == RelationshipConfidence.CONFIRMED_STATIC:
                confirmed_count += 1
            elif ent.relationship_type == RelationshipConfidence.POTENTIAL:
                potential_count += 1
            else:
                unknown_count += 1

        for lim in change_graph_report.graph_limitations:
            if "Unresolved repository import" in lim or "Source code unavailable" in lim or "syntax error" in lim.lower():
                unknown_count += 1

        # 5. Evaluate PR-wide Risk Factors
        pr_factors = self._evaluate_pr_factors(
            change_graph_report=change_graph_report,
            file_metrics=file_metrics,
            entity_risks=entity_risks,
        )

        # 6. Synthesize Overall PR Risk Level and Score
        overall_level, overall_score, high_reasons = self._synthesize_overall_risk(
            pr_factors=pr_factors,
            entity_risks=entity_risks,
            change_graph_report=change_graph_report,
            file_metrics=file_metrics,
            primary_impact_paths=primary_impact_paths,
        )

        # 7. Generate Explainable Summary
        summary = self._generate_summary(
            overall_level=overall_level,
            overall_score=overall_score,
            change_graph_report=change_graph_report,
            file_metrics=file_metrics,
            high_reasons=high_reasons,
        )

        return PRRiskAssessment(
            overall_risk_level=overall_level,
            overall_risk_score=round(overall_score, 2),
            summary=summary,
            high_risk_reasons=high_reasons,
            primary_impact_paths=primary_impact_paths,
            confirmed_relationships_count=confirmed_count,
            potential_relationships_count=potential_count,
            unknown_relationships_count=unknown_count,
            risk_factors=pr_factors,
            entity_risks=entity_risks,
            file_risks=file_risks,
            limitations=limitations + change_graph_report.graph_limitations,
        )

    # -------------------------------------------------------------------------
    # Entity-level evaluation
    # -------------------------------------------------------------------------

    def _evaluate_entities(
        self,
        change_graph_report: ChangeGraphReport,
        graph: Optional[nx.DiGraph],
        file_metrics: Dict[str, Dict[str, Any]],
    ) -> (List[EntityRiskDetail], List[ImpactPath]):
        """Rank and trace risk for directly changed and downstream impacted entities."""
        entity_risks: List[EntityRiskDetail] = []
        high_risk_paths: List[ImpactPath] = []

        # Map each directly changed entity to true downstream dependents (excluding the entity's own home file container)
        dependents_by_source: Dict[str, List[ImpactedEntity]] = {}
        for changed_id in change_graph_report.changed_entities:
            dependents_by_source[changed_id] = []

        for imp_entity in change_graph_report.impacted_entities:
            for path in imp_entity.impact_paths:
                if path.path_nodes:
                    source_id = path.path_nodes[0]
                    if source_id in dependents_by_source:
                        # Exclude the changed entity's own enclosing file from being counted as a downstream caller
                        source_file = source_id.replace("entity:", "").split("::")[0].replace("file:", "")
                        if imp_entity.node_id == f"file:{source_file}" and len(path.path_nodes) == 2 and "enclosed in" in path.path_description:
                            continue

                        if imp_entity not in dependents_by_source[source_id]:
                            dependents_by_source[source_id].append(imp_entity)

        # 1. Evaluate Directly Changed Entities
        for changed_node in change_graph_report.changed_entities:
            dependents = dependents_by_source.get(changed_node, [])
            dep_entities_count = len(dependents)
            dep_files = {d.file_path for d in dependents if d.file_path}
            dep_files_count = len(dep_files)
            max_depth = max([d.min_distance for d in dependents], default=0)

            node_attrs = graph.nodes[changed_node] if (graph and graph.has_node(changed_node)) else {}
            node_name = node_attrs.get("name", changed_node.split("::")[-1] if "::" in changed_node else changed_node)
            node_type = str(node_attrs.get("node_type", NodeType.FUNCTION).value if hasattr(node_attrs.get("node_type", ""), "value") else node_attrs.get("node_type", "function"))
            file_path = node_attrs.get("file_path", changed_node.replace("file:", "").split("::")[0])

            # Check associated hunk intent
            f_metric = file_metrics.get(file_path, {})
            has_unexplained_hunk = f_metric.get("unexplained_hunks", 0) > 0
            has_uncertain_hunk = f_metric.get("uncertain_hunks", 0) > 0

            # Factors
            factors: List[RiskFactor] = []
            reasons: List[str] = []

            # Factor A: Blast radius
            blast_score = min(1.0, (dep_entities_count * 0.2 + dep_files_count * 0.25 + max_depth * 0.15))
            if dep_entities_count >= 4 or dep_files_count >= 2 or max_depth >= 3:
                blast_level = RiskLevel.HIGH
                factors.append(
                    RiskFactor(
                        name="Downstream Blast Radius",
                        level=blast_level,
                        score=round(blast_score, 2),
                        description="Direct modification impacts broad downstream callers and dependent files.",
                        evidence=[
                            f"{dep_entities_count} downstream impacted entities",
                            f"{dep_files_count} downstream dependent files",
                            f"Max propagation depth of {max_depth} hops",
                        ],
                    )
                )
                reasons.append(
                    f"Broad downstream impact: {dep_entities_count} entities in {dep_files_count} files depend on this change (depth {max_depth})."
                )
            elif dep_entities_count >= 1:
                blast_level = RiskLevel.MEDIUM
                factors.append(
                    RiskFactor(
                        name="Downstream Blast Radius",
                        level=blast_level,
                        score=round(blast_score, 2),
                        description="Direct modification affects known downstream caller(s).",
                        evidence=[f"{dep_entities_count} downstream entity callers in {dep_files_count} file(s)"],
                    )
                )
                reasons.append(f"Direct callers affected: {dep_entities_count} downstream entity dependent(s).")
            else:
                blast_level = RiskLevel.LOW
                factors.append(
                    RiskFactor(
                        name="Downstream Blast Radius",
                        level=blast_level,
                        score=0.1,
                        description="Localized modification with zero downstream callers found in repository.",
                        evidence=["No downstream callers or importing files identified in AST."],
                    )
                )
                reasons.append("Localized change: no repository-internal callers or importers depend on this symbol.")

            # Factor B: Intent Alignment
            if has_unexplained_hunk:
                intent_risk_level = RiskLevel.HIGH if dep_entities_count >= 2 else RiskLevel.MEDIUM
                intent_score = 0.8 if dep_entities_count >= 2 else 0.45
                factors.append(
                    RiskFactor(
                        name="Intent Alignment",
                        level=intent_risk_level,
                        score=intent_score,
                        description="Hunk modification is not explained by stated PR title or description.",
                        evidence=["Contains changes flagged as UNEXPLAINED by intent analyzer."],
                    )
                )
                reasons.append("Contains unexplained code changes diverging from stated PR intent.")
            elif has_uncertain_hunk:
                factors.append(
                    RiskFactor(
                        name="Intent Alignment",
                        level=RiskLevel.MEDIUM,
                        score=0.35,
                        description="Hunk intent alignment is ambiguous or uncertain.",
                        evidence=["Contains changes flagged as UNCERTAIN."],
                    )
                )

            # Determine entity risk level
            if blast_level == RiskLevel.HIGH or (blast_level == RiskLevel.MEDIUM and has_unexplained_hunk and dep_entities_count >= 2):
                ent_level = RiskLevel.HIGH
                ent_score = max(0.7, blast_score)
            elif blast_level == RiskLevel.MEDIUM or has_unexplained_hunk or has_uncertain_hunk:
                ent_level = RiskLevel.MEDIUM
                ent_score = max(0.35, blast_score)
            else:
                ent_level = RiskLevel.LOW
                ent_score = 0.15

            # Gather paths originating from this entity
            entity_paths: List[ImpactPath] = []
            for dep in dependents:
                for p in dep.impact_paths:
                    if p.path_nodes and p.path_nodes[0] == changed_node:
                        entity_paths.append(p)
                        if ent_level == RiskLevel.HIGH and p not in high_risk_paths:
                            high_risk_paths.append(p)

            entity_risks.append(
                EntityRiskDetail(
                    node_id=changed_node,
                    name=node_name,
                    entity_type=node_type,
                    file_path=file_path,
                    is_directly_changed=True,
                    risk_level=ent_level,
                    risk_score=round(ent_score, 2),
                    relationship_type=RelationshipConfidence.CONFIRMED_STATIC,
                    min_distance=0,
                    dependent_entities_count=dep_entities_count,
                    dependent_files_count=dep_files_count,
                    impact_paths=entity_paths[:5],
                    reasons=reasons,
                    factors=factors,
                )
            )

        # 2. Evaluate Downstream Impacted Entities
        for imp in change_graph_report.impacted_entities:
            # Check if this is merely an enclosing file container
            is_file_node = imp.node_id.startswith("file:")
            rel_type = (
                RelationshipConfidence.CONFIRMED_STATIC
                if imp.min_distance == 1
                else RelationshipConfidence.POTENTIAL
            )

            # Check if file has syntax error or missing source
            f_attrs = graph.nodes.get(f"file:{imp.file_path}", {}) if graph else {}
            if f_attrs.get("metadata", {}).get("has_syntax_errors") or not f_attrs.get("metadata", {}).get("source_available", True):
                rel_type = RelationshipConfidence.UNKNOWN

            reasons: List[str] = []
            factors: List[RiskFactor] = []

            if is_file_node and imp.min_distance == 1 and all("enclosed in" in p.path_description for p in imp.impact_paths):
                ent_score = 0.15
                ent_level = RiskLevel.LOW
                reasons.append(f"Enclosing file container for modified entity.")
                factors.append(
                    RiskFactor(
                        name="Enclosing File Container",
                        level=RiskLevel.LOW,
                        score=ent_score,
                        description="Enclosing file module definition.",
                        evidence=[f"Contains modified entity in {imp.file_path}"],
                    )
                )
            elif imp.min_distance == 1:
                reasons.append(f"Direct downstream dependent: calls or imports modified entity at distance 1.")
                ent_score = 0.45
                ent_level = RiskLevel.MEDIUM
                factors.append(
                    RiskFactor(
                        name="Direct Call Dependency",
                        level=RiskLevel.MEDIUM,
                        score=ent_score,
                        description="Directly invokes or imports changed code in AST.",
                        evidence=[p.path_description for p in imp.impact_paths[:2]],
                    )
                )
            elif imp.min_distance == 2:
                reasons.append(f"Indirect downstream dependent (2 hops from changed code).")
                ent_score = 0.35
                ent_level = RiskLevel.MEDIUM
                factors.append(
                    RiskFactor(
                        name="Transitive Dependency",
                        level=RiskLevel.MEDIUM,
                        score=ent_score,
                        description="Indirect downstream dependency through intermediate caller.",
                        evidence=[p.path_description for p in imp.impact_paths[:2]],
                    )
                )
            else:
                reasons.append(f"Distant downstream dependent ({imp.min_distance} hops from changed code).")
                ent_score = 0.2
                ent_level = RiskLevel.LOW
                factors.append(
                    RiskFactor(
                        name="Transitive Dependency",
                        level=RiskLevel.LOW,
                        score=ent_score,
                        description="Deep transitive relationship.",
                        evidence=[f"Distance of {imp.min_distance} hops"],
                    )
                )

            entity_risks.append(
                EntityRiskDetail(
                    node_id=imp.node_id,
                    name=imp.name,
                    entity_type=imp.entity_type.value if hasattr(imp.entity_type, "value") else str(imp.entity_type),
                    file_path=imp.file_path,
                    is_directly_changed=False,
                    risk_level=ent_level,
                    risk_score=round(ent_score, 2),
                    relationship_type=rel_type,
                    min_distance=imp.min_distance,
                    dependent_entities_count=0,
                    dependent_files_count=0,
                    impact_paths=imp.impact_paths[:5],
                    reasons=reasons,
                    factors=factors,
                )
            )

        # Sort entity risks: HIGH first, then by risk_score desc, then distance asc
        entity_risks.sort(
            key=lambda e: (
                0 if e.risk_level == RiskLevel.HIGH else (1 if e.risk_level == RiskLevel.MEDIUM else 2),
                -e.risk_score,
                e.min_distance,
            )
        )

        return entity_risks, high_risk_paths

    # -------------------------------------------------------------------------
    # File-level evaluation
    # -------------------------------------------------------------------------

    def _evaluate_files(
        self,
        file_reports: List[FileAnalysisReport],
        file_metrics: Dict[str, Dict[str, Any]],
        entity_risks: List[EntityRiskDetail],
        change_graph_report: ChangeGraphReport,
    ) -> List[FileRiskDetail]:
        """Aggregate risk rankings per changed and impacted file."""
        file_risks: List[FileRiskDetail] = []
        entities_by_file: Dict[str, List[EntityRiskDetail]] = {}
        for ent in entity_risks:
            entities_by_file.setdefault(ent.file_path, []).append(ent)

        # Evaluate files appearing in PR file reports
        for f_rep in file_reports:
            f_name = f_rep.filename
            metric = file_metrics.get(f_name, {})
            ents = entities_by_file.get(f_name, [])

            direct_ents = [e for e in ents if e.is_directly_changed]
            impacted_ents = [e for e in ents if not e.is_directly_changed]

            additions = metric.get("additions", 0)
            deletions = metric.get("deletions", 0)
            unexplained = metric.get("unexplained_hunks", 0)
            uncertain = metric.get("uncertain_hunks", 0)
            hunks_count = f_rep.hunks_count

            # Check if any entity in this file is HIGH risk
            has_high_ent = any(e.risk_level == RiskLevel.HIGH for e in direct_ents)
            has_med_ent = any(e.risk_level == RiskLevel.MEDIUM for e in direct_ents)
            max_dep_entities = max([e.dependent_entities_count for e in direct_ents], default=0)

            factors: List[RiskFactor] = []
            reasons: List[str] = []

            # Factor 1: Code Volatility
            lines_changed = additions + deletions
            if lines_changed > 100 or hunks_count > 5:
                factors.append(
                    RiskFactor(
                        name="Code Volatility",
                        level=RiskLevel.HIGH,
                        score=0.8,
                        description="Substantial diff volume across multiple hunks.",
                        evidence=[f"{lines_changed} lines changed ({additions}+ / {deletions}-) in {hunks_count} hunks"],
                    )
                )
                reasons.append(f"High diff volume: {lines_changed} lines modified across {hunks_count} hunks.")
            elif lines_changed > 30 or hunks_count > 2:
                factors.append(
                    RiskFactor(
                        name="Code Volatility",
                        level=RiskLevel.MEDIUM,
                        score=0.45,
                        description="Moderate diff volume.",
                        evidence=[f"{lines_changed} lines changed in {hunks_count} hunks"],
                    )
                )
                reasons.append(f"Moderate diff volume: {lines_changed} lines changed in {hunks_count} hunks.")
            else:
                factors.append(
                    RiskFactor(
                        name="Code Volatility",
                        level=RiskLevel.LOW,
                        score=0.15,
                        description="Small localized diff.",
                        evidence=[f"{lines_changed} lines changed in {hunks_count} hunks"],
                    )
                )

            # Factor 2: Structural Blast Radius
            if max_dep_entities >= 4:
                reasons.append(f"Entities in this file have broad blast radius ({max_dep_entities} downstream dependents).")
            elif max_dep_entities >= 1:
                reasons.append(f"Modified entities affect {max_dep_entities} downstream dependents.")

            # Factor 3: Intent Alignment
            if unexplained > 0:
                reasons.append(f"{unexplained} hunk(s) contain unexplained changes diverging from PR intent.")
            elif uncertain > 0:
                reasons.append(f"{uncertain} hunk(s) have uncertain intent alignment.")

            # Factor 4: Limitations / Blind spots
            for lim in f_rep.limitations:
                if "unavailable" in lim.lower() or "syntax error" in lim.lower() or "unresolved" in lim.lower():
                    reasons.append(f"Analysis limitation: {lim}")
                    factors.append(
                        RiskFactor(
                            name="Analysis Limitation",
                            level=RiskLevel.MEDIUM,
                            score=0.5,
                            description="Incomplete AST extraction or unparsed code introduces blind spots.",
                            evidence=[lim],
                        )
                    )

            # Assign file risk level
            if has_high_ent or (lines_changed > 100 and max_dep_entities >= 2):
                f_level = RiskLevel.HIGH
                f_score = 0.8
            elif has_med_ent or unexplained > 0 or lines_changed > 30 or len(f_rep.limitations) > 0 or max_dep_entities >= 1:
                f_level = RiskLevel.MEDIUM
                f_score = 0.45
            else:
                f_level = RiskLevel.LOW
                f_score = 0.15
                if not reasons:
                    reasons.append("Localized change with low churn, full intent alignment, and no downstream callers.")

            file_risks.append(
                FileRiskDetail(
                    filename=f_name,
                    risk_level=f_level,
                    risk_score=round(f_score, 2),
                    directly_changed_entities=len(direct_ents),
                    impacted_entities_count=len(impacted_ents),
                    hunks_count=hunks_count,
                    added_lines=additions,
                    deleted_lines=deletions,
                    unexplained_hunks_count=unexplained,
                    uncertain_hunks_count=uncertain,
                    reasons=reasons,
                    factors=factors,
                )
            )

        return file_risks

    # -------------------------------------------------------------------------
    # PR-wide synthesis
    # -------------------------------------------------------------------------

    def _evaluate_pr_factors(
        self,
        change_graph_report: ChangeGraphReport,
        file_metrics: Dict[str, Dict[str, Any]],
        entity_risks: List[EntityRiskDetail],
    ) -> List[RiskFactor]:
        """Generate PR-wide factor breakdown."""
        factors: List[RiskFactor] = []

        # Changed file paths
        changed_files = {
            c.replace("entity:", "").split("::")[0].replace("file:", "")
            for c in change_graph_report.changed_entities
        }

        # Filter true downstream impacted entities (excluding the home file container of changed entities)
        true_downstream = [
            e for e in change_graph_report.impacted_entities
            if not (e.node_id.startswith("file:") and e.file_path in changed_files and all("enclosed in" in p.path_description for p in e.impact_paths))
        ]
        total_imp_entities = len(true_downstream)
        downstream_files = {
            e.file_path for e in true_downstream if e.file_path and e.file_path not in changed_files
        }
        total_imp_files = len(downstream_files)
        max_depth = max([e.min_distance for e in true_downstream], default=0)

        # 1. Downstream Impact Blast Radius
        blast_score = min(1.0, (total_imp_entities * 0.20 + total_imp_files * 0.25 + max_depth * 0.15))
        if total_imp_entities >= 4 or total_imp_files >= 2 or max_depth >= 3:
            factors.append(
                RiskFactor(
                    name="Downstream Blast Radius",
                    level=RiskLevel.HIGH,
                    score=round(max(0.70, blast_score), 2),
                    description="PR modifications propagate to multiple downstream entities and external files.",
                    evidence=[
                        f"{total_imp_entities} downstream impacted entities",
                        f"{total_imp_files} downstream impacted files",
                        f"Max propagation depth of {max_depth} hops",
                    ],
                )
            )
        elif total_imp_entities >= 1 or total_imp_files >= 1:
            factors.append(
                RiskFactor(
                    name="Downstream Blast Radius",
                    level=RiskLevel.MEDIUM,
                    score=round(max(0.35, blast_score), 2),
                    description="PR modifications propagate to downstream caller(s) or dependent files.",
                    evidence=[
                        f"{total_imp_entities} downstream impacted entities",
                        f"{total_imp_files} downstream impacted files",
                    ],
                )
            )
        else:
            factors.append(
                RiskFactor(
                    name="Downstream Blast Radius",
                    level=RiskLevel.LOW,
                    score=0.1,
                    description="Zero downstream entity callers or importing files identified in repository.",
                    evidence=["Modifications are isolated to changed entities with no downstream AST dependents."],
                )
            )

        # 2. Change Scope & Volatility
        total_add = sum(m.get("additions", 0) for m in file_metrics.values())
        total_del = sum(m.get("deletions", 0) for m in file_metrics.values())
        total_lines = total_add + total_del
        total_hunks = sum(m.get("hunks_count", 0) for m in file_metrics.values())

        churn_score = min(1.0, total_lines / 200.0)
        if total_lines > 150 or total_hunks > 6:
            factors.append(
                RiskFactor(
                    name="Change Scope & Volatility",
                    level=RiskLevel.HIGH,
                    score=round(max(0.70, churn_score), 2),
                    description="Large volume of code modifications across multiple hunks.",
                    evidence=[f"{total_lines} total lines changed ({total_add}+ / {total_del}-) across {total_hunks} hunks"],
                )
            )
        elif total_lines > 40 or total_hunks > 2:
            factors.append(
                RiskFactor(
                    name="Change Scope & Volatility",
                    level=RiskLevel.MEDIUM,
                    score=round(max(0.35, churn_score), 2),
                    description="Moderate change volume requiring standard regression verification.",
                    evidence=[f"{total_lines} total lines changed across {total_hunks} hunks"],
                )
            )
        else:
            factors.append(
                RiskFactor(
                    name="Change Scope & Volatility",
                    level=RiskLevel.LOW,
                    score=round(max(0.05, churn_score), 2),
                    description="Low change volume localized to few lines.",
                    evidence=[f"{total_lines} lines changed across {total_hunks} hunk(s)"],
                )
            )

        # 3. Intent Alignment & Side Effects
        total_unexplained = sum(m.get("unexplained_hunks", 0) for m in file_metrics.values())
        total_uncertain = sum(m.get("uncertain_hunks", 0) for m in file_metrics.values())

        if total_unexplained > 0 and total_imp_entities >= 1:
            factors.append(
                RiskFactor(
                    name="Intent Alignment",
                    level=RiskLevel.HIGH,
                    score=0.85,
                    description="Unexplained code modifications combined with downstream impact detected.",
                    evidence=[
                        f"{total_unexplained} hunk(s) flagged UNEXPLAINED by intent analyzer",
                        f"Impacts {total_imp_entities} downstream entities",
                    ],
                )
            )
        elif total_unexplained > 0 or total_uncertain > 0:
            factors.append(
                RiskFactor(
                    name="Intent Alignment",
                    level=RiskLevel.MEDIUM,
                    score=0.45,
                    description="Ambiguous or unexplained hunks present; review recommended.",
                    evidence=[
                        f"{total_unexplained} unexplained hunk(s)",
                        f"{total_uncertain} uncertain hunk(s)",
                    ],
                )
            )
        else:
            factors.append(
                RiskFactor(
                    name="Intent Alignment",
                    level=RiskLevel.LOW,
                    score=0.1,
                    description="All changed hunks align with stated Pull Request intent.",
                    evidence=["Zero unexplained or anomalous hunks identified."],
                )
            )

        # 4. Dependency Resolvability & Blind Spots
        graph_lims = change_graph_report.graph_limitations
        unresolved_internal = [l for l in graph_lims if "Unresolved repository import" in l]
        missing_source = [l for l in graph_lims if "Source code unavailable" in l]
        syntax_errors = [l for l in graph_lims if "syntax error" in l.lower()]

        if len(unresolved_internal) >= 3 or len(syntax_errors) >= 2:
            factors.append(
                RiskFactor(
                    name="Dependency Graph Resolvability",
                    level=RiskLevel.HIGH,
                    score=0.8,
                    description="Significant internal imports or syntax errors introduce major blast radius blind spots.",
                    evidence=unresolved_internal[:2] + syntax_errors[:2],
                )
            )
        elif len(unresolved_internal) > 0 or len(missing_source) > 0 or len(syntax_errors) > 0:
            factors.append(
                RiskFactor(
                    name="Dependency Graph Resolvability",
                    level=RiskLevel.MEDIUM,
                    score=0.45,
                    description="Partial AST or unresolved internal import introducing analysis blind spots and limitations.",
                    evidence=(unresolved_internal + missing_source + syntax_errors)[:3],
                )
            )
        else:
            factors.append(
                RiskFactor(
                    name="Dependency Graph Resolvability",
                    level=RiskLevel.LOW,
                    score=0.05,
                    description="All repository internal imports and code entities fully resolved in AST.",
                    evidence=["100% internal imports and AST entities statically verified."],
                )
            )

        return factors

    def _synthesize_overall_risk(
        self,
        pr_factors: List[RiskFactor],
        entity_risks: List[EntityRiskDetail],
        change_graph_report: ChangeGraphReport,
        file_metrics: Dict[str, Dict[str, Any]],
        primary_impact_paths: List[ImpactPath],
    ) -> (RiskLevel, float, List[str]):
        """Determine overall PR risk tier and gather supporting high-risk reasons."""
        high_reasons: List[str] = []

        # Count factor levels
        factor_map = {f.name: f for f in pr_factors}
        blast_factor = factor_map.get("Downstream Blast Radius")
        churn_factor = factor_map.get("Change Scope & Volatility")
        intent_factor = factor_map.get("Intent Alignment")
        resolvability_factor = factor_map.get("Dependency Graph Resolvability")

        high_entities = [e for e in entity_risks if e.risk_level == RiskLevel.HIGH]
        med_entities = [e for e in entity_risks if e.risk_level == RiskLevel.MEDIUM]

        # Explicit Rules for HIGH:
        # Rule 1: High blast radius (>= 4 downstream entities or >= 2 external files or depth >= 3)
        if blast_factor and blast_factor.level == RiskLevel.HIGH:
            high_reasons.append(
                f"High downstream blast radius: {blast_factor.evidence[0]} and "
                f"{blast_factor.evidence[1]}."
            )

        # Rule 2: Unexplained changes with downstream impact
        if intent_factor and intent_factor.level == RiskLevel.HIGH:
            high_reasons.append(
                "Unexplained code changes with downstream dependents: modified code does not match stated PR intent "
                "and directly affects callers."
            )

        # Rule 3: High change volatility with downstream impact
        if churn_factor and churn_factor.level == RiskLevel.HIGH and (blast_factor and blast_factor.level != RiskLevel.LOW):
            high_reasons.append(
                f"Large diff volume ({churn_factor.evidence[0] if churn_factor.evidence else 'large change'}) "
                f"propagating to downstream dependencies."
            )

        # Rule 4: High graph uncertainty with multiple unresolved internal imports
        if resolvability_factor and resolvability_factor.level == RiskLevel.HIGH:
            high_reasons.append(
                "Critical internal dependencies or syntax errors could not be resolved, creating potential regression blind spots."
            )

        # Rule 5: Individual directly changed entity rated HIGH
        for e in high_entities:
            if e.is_directly_changed:
                for r in e.reasons:
                    if r not in high_reasons:
                        high_reasons.append(f"Entity '{e.name}': {r}")

        # Compute composite weighted score
        weights = {
            "Downstream Blast Radius": 0.40,
            "Change Scope & Volatility": 0.20,
            "Intent Alignment": 0.25,
            "Dependency Graph Resolvability": 0.15,
        }
        weighted_score = 0.0
        for f in pr_factors:
            w = weights.get(f.name, 0.25)
            weighted_score += f.score * w

        # Assign Level
        if len(high_reasons) > 0 or weighted_score >= 0.65:
            overall_level = RiskLevel.HIGH
            overall_score = max(0.70, weighted_score)
            # Ensure supporting impact paths exist for HIGH
            if not primary_impact_paths:
                for imp in change_graph_report.impacted_entities:
                    if imp.impact_paths:
                        primary_impact_paths.extend(imp.impact_paths[:2])
                        break
        elif (
            (blast_factor and blast_factor.level == RiskLevel.MEDIUM)
            or (churn_factor and churn_factor.level == RiskLevel.MEDIUM)
            or (intent_factor and intent_factor.level == RiskLevel.MEDIUM)
            or (resolvability_factor and resolvability_factor.level == RiskLevel.MEDIUM)
            or any(e.risk_level == RiskLevel.MEDIUM and e.is_directly_changed and e.dependent_entities_count >= 1 for e in entity_risks)
            or weighted_score >= 0.30
        ):
            overall_level = RiskLevel.MEDIUM
            overall_score = max(0.35, weighted_score)
        else:
            overall_level = RiskLevel.LOW
            overall_score = min(0.25, max(0.05, weighted_score))

        return overall_level, overall_score, high_reasons

    def _generate_summary(
        self,
        overall_level: RiskLevel,
        overall_score: float,
        change_graph_report: ChangeGraphReport,
        file_metrics: Dict[str, Dict[str, Any]],
        high_reasons: List[str],
    ) -> str:
        """Construct executive human-readable summary."""
        imp_count = change_graph_report.impacted_entities_count
        imp_files = change_graph_report.impacted_files_count
        total_files = len(file_metrics)

        if overall_level == RiskLevel.HIGH:
            lead = f"HIGH RISK (Score: {overall_score:.2f}) — Requires thorough architectural and regression review."
            reasons_summary = " ".join(high_reasons[:2])
            return f"{lead} {reasons_summary} Total downstream impact: {imp_count} entities across {imp_files} files."
        elif overall_level == RiskLevel.MEDIUM:
            return (
                f"MEDIUM RISK (Score: {overall_score:.2f}) — Moderate change scope affecting {imp_count} downstream entity callers "
                f"across {imp_files} dependent files. Standard targeted regression tests recommended."
            )
        else:
            return (
                f"LOW RISK (Score: {overall_score:.2f}) — Localized change with zero or minimal downstream callers. "
                f"Modifications in {total_files} file(s) align with stated PR intent with low regression blast radius."
            )

    # -------------------------------------------------------------------------
    # Helper utilities
    # -------------------------------------------------------------------------

    def _extract_file_metrics(
        self,
        file_reports: List[FileAnalysisReport],
        pr_details: Optional[PullRequestDetails],
    ) -> Dict[str, Dict[str, Any]]:
        """Index per-file additions, deletions, hunks, and intent classifications."""
        metrics: Dict[str, Dict[str, Any]] = {}

        # Seed from pr_details if available
        if pr_details:
            for f in pr_details.files:
                metrics[f.filename] = {
                    "additions": f.additions,
                    "deletions": f.deletions,
                    "hunks_count": 0,
                    "unexplained_hunks": 0,
                    "uncertain_hunks": 0,
                    "explained_hunks": 0,
                }

        # Enrich from file_reports
        for f_rep in file_reports:
            entry = metrics.setdefault(
                f_rep.filename,
                {
                    "additions": 0,
                    "deletions": 0,
                    "hunks_count": f_rep.hunks_count,
                    "unexplained_hunks": 0,
                    "uncertain_hunks": 0,
                    "explained_hunks": 0,
                },
            )
            entry["hunks_count"] = f_rep.hunks_count

            for h in f_rep.hunks:
                if h.classification == IntentClassification.UNEXPLAINED:
                    entry["unexplained_hunks"] += 1
                elif h.classification == IntentClassification.UNCERTAIN:
                    entry["uncertain_hunks"] += 1
                elif h.classification == IntentClassification.EXPLAINED:
                    entry["explained_hunks"] += 1

        return metrics
