"""Deterministic Regression Test Selection Engine (Milestone 7)."""
from __future__ import annotations
import logging
from typing import Dict, List, Optional, Set, Tuple
import networkx as nx

from backend.app.repository.models import ParseResult, CodeEntity, CodeEntityType
from backend.app.graph.models import ChangeGraphReport, NodeType
from backend.app.impact.models import PRRiskAssessment, RelationshipConfidence, RiskLevel
from backend.app.testing.models import (
    TestPriority,
    TestMatchType,
    SelectedTestCase,
    TestSelectionReport,
)

logger = logging.getLogger("changeguard.testing")


class RegressionTestSelector:
    """Selects and prioritizes targeted regression tests using AST call sites, static imports, and naming heuristics."""

    def select_tests(
        self,
        change_graph_report: ChangeGraphReport,
        test_parse_results: Dict[str, Optional[ParseResult]],
        risk_assessment: Optional[PRRiskAssessment] = None,
        graph: Optional[nx.DiGraph] = None,
    ) -> TestSelectionReport:
        """Run deterministic test selection based on changed and impacted entities.

        Args:
            change_graph_report: Milestone 5 change graph report.
            test_parse_results: Mapping of test file path to its ParseResult (or None if unparsed).
            risk_assessment: Optional Milestone 6 risk assessment report.
            graph: Optional NetworkX directed graph from Milestone 5.

        Returns:
            TestSelectionReport containing ranked recommended tests, priority counts, and evidence.
        """
        limitations: List[str] = [
            "Test selection is based on static AST call sites, imports, and naming conventions; dynamic pytest fixtures, mock patches, or parameterized test cases without static call sites may not be identified.",
            "ChangeGuard provides test recommendations for local or CI execution; arbitrary PR code is never executed automatically.",
        ]

        # 1. Index changed and impacted entities
        changed_entity_ids = set(change_graph_report.changed_entities)
        changed_symbols = {
            self._extract_symbol_name(e_id): e_id for e_id in changed_entity_ids
        }
        changed_files = {
            self._extract_file_path(e_id): e_id for e_id in changed_entity_ids
        }

        # Index downstream impacted entities
        impacted_by_id: Dict[str, int] = {}  # entity_id -> min_distance
        impacted_symbols: Dict[str, Tuple[str, int]] = {}  # symbol -> (entity_id, distance)
        for imp in change_graph_report.impacted_entities:
            impacted_by_id[imp.node_id] = imp.min_distance
            clean_sym = imp.name
            if clean_sym not in impacted_symbols or imp.min_distance < impacted_symbols[clean_sym][1]:
                impacted_symbols[clean_sym] = (imp.node_id, imp.min_distance)

        # 2. Discover test entities across test parse results
        total_tests_discovered = 0
        candidate_matches: Dict[str, SelectedTestCase] = {}

        for test_file, pr_result in test_parse_results.items():
            if not pr_result:
                limitations.append(f"Test file '{test_file}': Source code unavailable or unparsed.")
                continue

            # Identify if file is a test file
            if not self._is_test_file(test_file):
                continue

            test_entities = self._extract_test_entities(pr_result)
            total_tests_discovered += len(test_entities)

            # Analyze test file imports
            imported_modules = {imp.module for imp in pr_result.imports}
            imported_symbols = {
                imp.alias or imp.name: imp.module for imp in pr_result.imports if imp.name
            }

            # Check file-level naming heuristic match against changed files
            file_match_targets = self._match_test_file_to_changed_files(test_file, changed_files)

            # 3. Analyze each test entity
            for test_ent in test_entities:
                test_id = f"{test_file}::{test_ent.name}"
                matched_case: Optional[SelectedTestCase] = None

                # Rule A: Static Call to directly changed entity
                call_match = self._find_call_to_target(
                    test_ent=test_ent,
                    parse_result=pr_result,
                    target_entity_ids=changed_entity_ids,
                    target_symbols=changed_symbols,
                )
                if call_match:
                    target_id, target_symbol, line_no = call_match
                    matched_case = SelectedTestCase(
                        test_id=test_id,
                        test_name=test_ent.name,
                        test_file=test_file,
                        priority=TestPriority.P0_CRITICAL,
                        score=0.95,
                        match_type=TestMatchType.STATIC_CALL,
                        relationship_confidence=RelationshipConfidence.CONFIRMED_STATIC,
                        linked_entities=[target_id],
                        evidence=[
                            f"Direct AST invocation of modified entity '{target_symbol}' at line {line_no}."
                        ],
                        suggested_command=f"pytest {test_file} -k {test_ent.name}",
                    )

                # Rule B: Static Call to downstream impacted entity
                if not matched_case:
                    imp_call_match = self._find_call_to_impacted(
                        test_ent=test_ent,
                        parse_result=pr_result,
                        impacted_symbols=impacted_symbols,
                    )
                    if imp_call_match:
                        target_id, target_symbol, distance, line_no = imp_call_match
                        prio = TestPriority.P1_HIGH if distance == 1 else TestPriority.P2_MEDIUM
                        score = 0.80 if distance == 1 else 0.60
                        rel_conf = (
                            RelationshipConfidence.CONFIRMED_STATIC
                            if distance == 1
                            else RelationshipConfidence.POTENTIAL
                        )
                        matched_case = SelectedTestCase(
                            test_id=test_id,
                            test_name=test_ent.name,
                            test_file=test_file,
                            priority=prio,
                            score=score,
                            match_type=(
                                TestMatchType.STATIC_CALL
                                if distance == 1
                                else TestMatchType.TRANSITIVE_GRAPH
                            ),
                            relationship_confidence=rel_conf,
                            linked_entities=[target_id],
                            evidence=[
                                f"Invokes downstream impacted entity '{target_symbol}' (distance {distance} in dependency graph) at line {line_no}."
                            ],
                            suggested_command=f"pytest {test_file} -k {test_ent.name}",
                        )

                # Rule C: Symbol Naming Heuristic (e.g. test_calculate_discount -> calculate_discount)
                if not matched_case:
                    sym_heuristic = self._match_symbol_heuristic(test_ent.name, changed_symbols)
                    if sym_heuristic:
                        target_id, target_sym = sym_heuristic
                        imports_target_module = any(
                            mod in target_id for mod in imported_modules
                        ) or (target_sym in imported_symbols)

                        prio = TestPriority.P0_CRITICAL if imports_target_module else TestPriority.P1_HIGH
                        score = 0.90 if imports_target_module else 0.75
                        rel_conf = (
                            RelationshipConfidence.CONFIRMED_STATIC
                            if imports_target_module
                            else RelationshipConfidence.POTENTIAL
                        )
                        evidence = [
                            f"Naming convention match: test function '{test_ent.name}' targets modified symbol '{target_sym}'."
                        ]
                        if imports_target_module:
                            evidence.append(f"Test module imports source module containing '{target_sym}'.")
                        else:
                            evidence.append("Heuristic symbol correlation without confirmed direct import.")

                        matched_case = SelectedTestCase(
                            test_id=test_id,
                            test_name=test_ent.name,
                            test_file=test_file,
                            priority=prio,
                            score=score,
                            match_type=TestMatchType.NAMING_HEURISTIC,
                            relationship_confidence=rel_conf,
                            linked_entities=[target_id],
                            evidence=evidence,
                            suggested_command=f"pytest {test_file} -k {test_ent.name}",
                        )

                # Rule D: Test module directly imports changed file
                if not matched_case:
                    imp_file_match = self._match_module_import(
                        imported_modules=imported_modules,
                        changed_files=changed_files,
                    )
                    if imp_file_match:
                        mod_name, matched_file_id = imp_file_match
                        matched_case = SelectedTestCase(
                            test_id=test_id,
                            test_name=test_ent.name,
                            test_file=test_file,
                            priority=TestPriority.P1_HIGH,
                            score=0.70,
                            match_type=TestMatchType.STATIC_IMPORT,
                            relationship_confidence=RelationshipConfidence.CONFIRMED_STATIC,
                            linked_entities=[matched_file_id],
                            evidence=[
                                f"Test module '{test_file}' statically imports modified module '{mod_name}'."
                            ],
                            suggested_command=f"pytest {test_file} -k {test_ent.name}",
                        )

                # Rule E: File-level naming heuristic match (e.g. test_billing.py -> billing.py)
                if not matched_case and file_match_targets:
                    matched_file = file_match_targets[0]
                    matched_case = SelectedTestCase(
                        test_id=test_id,
                        test_name=test_ent.name,
                        test_file=test_file,
                        priority=TestPriority.P2_MEDIUM,
                        score=0.55,
                        match_type=TestMatchType.NAMING_HEURISTIC,
                        relationship_confidence=RelationshipConfidence.POTENTIAL,
                        linked_entities=[f"file:{matched_file}"],
                        evidence=[
                            f"File-level naming heuristic: test suite '{test_file}' corresponds to changed file '{matched_file}'."
                        ],
                        suggested_command=f"pytest {test_file} -k {test_ent.name}",
                    )

                if matched_case:
                    # Keep best match for test_id
                    if test_id not in candidate_matches or candidate_matches[test_id].score < matched_case.score:
                        candidate_matches[test_id] = matched_case

        # 4. Rank candidate tests
        recommended_tests = list(candidate_matches.values())
        recommended_tests.sort(
            key=lambda t: (
                0 if t.priority == TestPriority.P0_CRITICAL else (
                    1 if t.priority == TestPriority.P1_HIGH else (
                        2 if t.priority == TestPriority.P2_MEDIUM else 3
                    )
                ),
                -t.score,
                t.test_file,
                t.test_name,
            )
        )

        critical_count = sum(1 for t in recommended_tests if t.priority == TestPriority.P0_CRITICAL)
        high_count = sum(1 for t in recommended_tests if t.priority == TestPriority.P1_HIGH)
        medium_count = sum(1 for t in recommended_tests if t.priority == TestPriority.P2_MEDIUM)
        low_count = sum(1 for t in recommended_tests if t.priority == TestPriority.P3_LOW)

        # 5. Synthesize Executive Summary
        if not recommended_tests:
            if total_tests_discovered == 0:
                summary = (
                    "No supported Python test suites or test functions discovered for modified components. "
                    "Reviewers should verify test coverage manually or add new regression tests."
                )
            else:
                summary = (
                    f"Discovered {total_tests_discovered} test cases across repository, but none statically link "
                    f"to the modified or downstream impacted entities."
                )
        else:
            summary = (
                f"Selected {len(recommended_tests)} targeted regression test(s) ({critical_count} critical, "
                f"{high_count} high, {medium_count} medium) covering changed and downstream impacted code."
            )

        return TestSelectionReport(
            total_tests_discovered=total_tests_discovered,
            selected_tests_count=len(recommended_tests),
            critical_count=critical_count,
            high_count=high_count,
            medium_count=medium_count,
            low_count=low_count,
            summary=summary,
            recommended_tests=recommended_tests,
            selection_strategy="AST Call Graph Traversal + Static Imports + Transparent Naming Heuristics",
            limitations=limitations,
        )

    # -------------------------------------------------------------------------
    # Helper resolution methods
    # -------------------------------------------------------------------------

    @staticmethod
    def _is_test_file(file_path: str) -> bool:
        """Determines if a relative file path is a Python test file."""
        norm = file_path.replace("\\", "/").lower()
        if not norm.endswith(".py"):
            return False
        base = norm.split("/")[-1]
        return (
            base.startswith("test_")
            or base.endswith("_test.py")
            or "/tests/" in norm
            or "/test/" in norm
            or norm.startswith("test_")
        )

    @staticmethod
    def _extract_test_entities(parse_result: ParseResult) -> List[CodeEntity]:
        """Extract test functions, test methods, and test classes from parse result."""
        tests: List[CodeEntity] = []
        if not parse_result.entities:
            return tests

        for ent in parse_result.entities:
            name_lower = ent.name.lower()
            if ent.entity_type in (CodeEntityType.FUNCTION, CodeEntityType.METHOD):
                if name_lower.startswith("test_") or name_lower.endswith("_test") or name_lower == "test":
                    tests.append(ent)
            elif ent.entity_type == CodeEntityType.CLASS:
                if name_lower.startswith("test") or name_lower.endswith("test") or name_lower.endswith("testcase"):
                    tests.append(ent)
        return tests

    def _find_call_to_target(
        self,
        test_ent: CodeEntity,
        parse_result: ParseResult,
        target_entity_ids: Set[str],
        target_symbols: Dict[str, str],
    ) -> Optional[Tuple[str, str, int]]:
        """Check if test entity invokes any directly changed entity."""
        for call in parse_result.call_sites:
            if call.caller_entity_id and call.caller_entity_id != test_ent.id:
                continue

            callee_sym = self._clean_callee_name(call.callee_name)
            if callee_sym in target_symbols:
                target_id = target_symbols[callee_sym]
                return target_id, callee_sym, call.line_number
        return None

    def _find_call_to_impacted(
        self,
        test_ent: CodeEntity,
        parse_result: ParseResult,
        impacted_symbols: Dict[str, Tuple[str, int]],
    ) -> Optional[Tuple[str, str, int, int]]:
        """Check if test entity invokes any downstream impacted entity."""
        for call in parse_result.call_sites:
            if call.caller_entity_id and call.caller_entity_id != test_ent.id:
                continue

            callee_sym = self._clean_callee_name(call.callee_name)
            if callee_sym in impacted_symbols:
                target_id, distance = impacted_symbols[callee_sym]
                return target_id, callee_sym, distance, call.line_number
        return None

    @staticmethod
    def _match_symbol_heuristic(
        test_name: str,
        changed_symbols: Dict[str, str],
    ) -> Optional[Tuple[str, str]]:
        """Match test name against changed symbols using naming conventions."""
        name_clean = test_name.lower()
        if name_clean.startswith("test_"):
            target_candidate = name_clean[5:]
        elif name_clean.endswith("_test"):
            target_candidate = name_clean[:-5]
        else:
            target_candidate = name_clean

        for sym, target_id in changed_symbols.items():
            sym_clean = sym.lower()
            if target_candidate == sym_clean or target_candidate.startswith(f"{sym_clean}_") or target_candidate.endswith(f"_{sym_clean}"):
                return target_id, sym
        return None

    @staticmethod
    def _match_module_import(
        imported_modules: Set[str],
        changed_files: Dict[str, str],
    ) -> Optional[Tuple[str, str]]:
        """Check if test module imports any changed source file."""
        for mod in imported_modules:
            mod_path = mod.replace(".", "/")
            for chg_file, chg_id in changed_files.items():
                if chg_file.startswith(mod_path) or mod_path in chg_file:
                    return mod, chg_id
        return None

    @staticmethod
    def _match_test_file_to_changed_files(
        test_file: str,
        changed_files: Dict[str, str],
    ) -> List[str]:
        """Correlate test file name with changed source files (e.g. test_billing.py -> app/billing.py)."""
        matches: List[str] = []
        test_base = test_file.replace("\\", "/").split("/")[-1].replace(".py", "")
        if test_base.startswith("test_"):
            core_name = test_base[5:]
        elif test_base.endswith("_test"):
            core_name = test_base[:-5]
        else:
            core_name = test_base

        for chg_file in changed_files.keys():
            chg_base = chg_file.replace("\\", "/").split("/")[-1].replace(".py", "")
            if core_name == chg_base or core_name.startswith(f"{chg_base}_") or core_name.endswith(f"_{chg_base}"):
                matches.append(chg_file)
        return matches

    @staticmethod
    def _clean_callee_name(callee_name: str) -> str:
        """Strip prefixes like 'self.', 'cls.', or module prefixes."""
        if callee_name.startswith("self."):
            callee_name = callee_name[5:]
        elif callee_name.startswith("cls."):
            callee_name = callee_name[4:]
        if "." in callee_name:
            callee_name = callee_name.split(".")[-1]
        return callee_name

    @staticmethod
    def _extract_symbol_name(node_id: str) -> str:
        """Extract symbol name from node ID."""
        clean = node_id.replace("entity:", "").replace("file:", "")
        if "::" in clean:
            return clean.split("::")[-1].split(".")[-1]
        return clean.split("/")[-1].replace(".py", "")

    @staticmethod
    def _extract_file_path(node_id: str) -> str:
        """Extract file path from node ID."""
        clean = node_id.replace("entity:", "").replace("file:", "")
        if "::" in clean:
            return clean.split("::")[0]
        return clean
