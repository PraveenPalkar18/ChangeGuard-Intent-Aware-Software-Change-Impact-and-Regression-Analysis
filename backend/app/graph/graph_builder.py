"""Directed Change and Dependency Graph builder using NetworkX (Milestone 5 & Improvements)."""
import logging
from typing import Dict, List, Set, Optional, Tuple, Any
from collections import deque
import networkx as nx

from backend.app.repository.models import (
    ParseResult,
    CodeEntity,
    CodeEntityType,
    ImportEntity,
    CallSite,
)
from backend.app.graph.models import (
    NodeType,
    EdgeType,
    RelationshipCertainty,
    GraphNode,
    GraphEdge,
    ImpactPath,
    ImpactedEntity,
    ChangeGraphReport,
)

logger = logging.getLogger("changeguard.graph")


class ChangeGraphBuilder:
    """Constructs and queries the repository change and dependency graph."""

    def __init__(self):
        self._graph = nx.DiGraph()
        self._limitations: List[str] = []
        self._entity_lookup: Dict[str, str] = {}  # short name / qualified name -> node_id

    @property
    def graph(self) -> nx.DiGraph:
        return self._graph

    def build_from_parse_results(
        self,
        parse_results: Dict[str, Optional[ParseResult]],
        file_statuses: Optional[Dict[str, str]] = None,
    ) -> None:
        """Populate the graph from file parse results.

        Args:
            parse_results: Mapping of relative file path to its ParseResult (or None if unavailable/unparsed).
            file_statuses: Optional mapping of file path to change status ('added', 'modified', etc.).
        """
        file_statuses = file_statuses or {}

        # 1. Add File Nodes
        for file_path, pr_result in parse_results.items():
            file_node_id = f"file:{file_path}"
            short_name = file_path.replace("\\", "/").split("/")[-1]
            has_error = pr_result.has_syntax_errors if pr_result else False
            is_unsupported = (pr_result.language != "python") if pr_result else False

            self._graph.add_node(
                file_node_id,
                id=file_node_id,
                name=short_name,
                node_type=NodeType.FILE,
                file_path=file_path,
                start_line=1,
                end_line=pr_result.raw_loc if pr_result else None,
                metadata={
                    "status": file_statuses.get(file_path, "unknown"),
                    "has_syntax_errors": has_error,
                    "is_unsupported": is_unsupported,
                    "source_available": pr_result is not None,
                },
            )

            if not pr_result:
                self._limitations.append(
                    f"File '{file_path}': Source code unavailable or unparsed; file node created without entity hierarchy."
                )
            elif pr_result.has_syntax_errors:
                self._limitations.append(
                    f"File '{file_path}': AST contains syntax error nodes; entity graph may be partial."
                )

        # 2. Add CodeEntity Nodes and CONTAINS Edges
        for file_path, pr_result in parse_results.items():
            if not pr_result or not pr_result.entities:
                continue

            file_node_id = f"file:{file_path}"
            for entity in pr_result.entities:
                entity_node_id = f"entity:{entity.id}"
                node_type = self._map_entity_type(entity.entity_type)

                self._graph.add_node(
                    entity_node_id,
                    id=entity_node_id,
                    name=entity.name,
                    node_type=node_type,
                    file_path=entity.file_path,
                    start_line=entity.start_line,
                    end_line=entity.end_line,
                    metadata={
                        "parent_id": entity.parent_id,
                        "parameters": entity.parameters,
                        "decorators": entity.decorators,
                        "is_async": entity.is_async,
                        "base_classes": getattr(entity, "base_classes", []),
                    },
                )

                # Maintain lookup indices for call/import resolution
                self._entity_lookup[entity.id] = entity_node_id
                self._entity_lookup[f"{entity.file_path}::{entity.name}"] = entity_node_id
                self._entity_lookup[f"{file_path}#{entity.name}"] = entity_node_id
                if entity.name not in self._entity_lookup:
                    self._entity_lookup[entity.name] = entity_node_id

                # Add containment edge
                if entity.parent_id:
                    parent_node_id = f"entity:{entity.parent_id}"
                    if self._graph.has_node(parent_node_id):
                        self._graph.add_edge(
                            parent_node_id,
                            entity_node_id,
                            edge_type=EdgeType.CONTAINS,
                            source_file=file_path,
                            source_line=None,
                            target_file=file_path,
                            target_line=entity.start_line,
                            detection_method="ast_containment",
                            certainty=RelationshipCertainty.CONFIRMED,
                            evidence="Enclosing class contains member",
                            metadata={"relationship": "parent_to_child"},
                        )
                    else:
                        self._graph.add_edge(
                            file_node_id,
                            entity_node_id,
                            edge_type=EdgeType.CONTAINS,
                            source_file=file_path,
                            source_line=1,
                            target_file=file_path,
                            target_line=entity.start_line,
                            detection_method="ast_containment",
                            certainty=RelationshipCertainty.CONFIRMED,
                            evidence="File contains top-level entity",
                            metadata={"relationship": "file_to_entity"},
                        )
                else:
                    self._graph.add_edge(
                        file_node_id,
                        entity_node_id,
                        edge_type=EdgeType.CONTAINS,
                        source_file=file_path,
                        source_line=1,
                        target_file=file_path,
                        target_line=entity.start_line,
                        detection_method="ast_containment",
                        certainty=RelationshipCertainty.CONFIRMED,
                        evidence="File contains top-level entity",
                        metadata={"relationship": "file_to_entity"},
                    )

        # 3. Add IMPORTS Edges
        for file_path, pr_result in parse_results.items():
            if not pr_result or not pr_result.imports:
                continue

            file_node_id = f"file:{file_path}"
            for imp in pr_result.imports:
                resolved_target = self._resolve_import(imp, parse_results)
                if resolved_target:
                    target_attrs = self._graph.nodes.get(resolved_target, {})
                    self._graph.add_edge(
                        file_node_id,
                        resolved_target,
                        edge_type=EdgeType.IMPORTS,
                        source_file=file_path,
                        source_line=imp.line_number,
                        target_file=target_attrs.get("file_path"),
                        target_line=target_attrs.get("start_line", 1),
                        detection_method="ast_import",
                        certainty=RelationshipCertainty.CONFIRMED,
                        evidence=f"Explicit import of module '{imp.module}' (symbol: '{imp.name or '*'}')",
                        metadata={
                            "module": imp.module,
                            "symbol": imp.name,
                            "alias": imp.alias,
                            "line_number": imp.line_number,
                            "is_from_import": imp.is_from_import,
                        },
                    )
                else:
                    if not imp.module.startswith((".", "app", "src", "backend")):
                        continue
                    self._limitations.append(
                        f"Unresolved repository import '{imp.module}' in '{file_path}:{imp.line_number}'"
                    )

        # 4. Add CALLS Edges
        for file_path, pr_result in parse_results.items():
            if not pr_result or not pr_result.call_sites:
                continue

            for call in pr_result.call_sites:
                caller_node_id = (
                    f"entity:{call.caller_entity_id}"
                    if call.caller_entity_id and self._graph.has_node(f"entity:{call.caller_entity_id}")
                    else f"file:{file_path}"
                )

                callee_node_id, call_certainty = self._resolve_call_with_certainty(call, file_path, pr_result)
                if callee_node_id and self._graph.has_node(callee_node_id):
                    callee_attrs = self._graph.nodes.get(callee_node_id, {})
                    self._graph.add_edge(
                        caller_node_id,
                        callee_node_id,
                        edge_type=EdgeType.CALLS,
                        source_file=file_path,
                        source_line=call.line_number,
                        target_file=callee_attrs.get("file_path"),
                        target_line=callee_attrs.get("start_line"),
                        detection_method="ast_call_site" if call_certainty == RelationshipCertainty.CONFIRMED else "symbol_fallback",
                        certainty=call_certainty,
                        evidence=f"Invocation of '{call.callee_name}' with {call.arguments_count} args",
                        metadata={
                            "callee_name": call.callee_name,
                            "line_number": call.line_number,
                            "arguments_count": call.arguments_count,
                        },
                    )

        # 5. Add INHERITS Edges (Class Inheritance)
        for file_path, pr_result in parse_results.items():
            if not pr_result or not pr_result.entities:
                continue

            for entity in pr_result.entities:
                if entity.entity_type == CodeEntityType.CLASS and getattr(entity, "base_classes", None):
                    subclass_node_id = f"entity:{entity.id}"
                    for base_name in entity.base_classes:
                        base_node_id = self._resolve_class_inheritance(base_name, file_path, pr_result)
                        if base_node_id and self._graph.has_node(base_node_id):
                            base_attrs = self._graph.nodes.get(base_node_id, {})
                            self._graph.add_edge(
                                subclass_node_id,
                                base_node_id,
                                edge_type=EdgeType.INHERITS,
                                source_file=file_path,
                                source_line=entity.start_line,
                                target_file=base_attrs.get("file_path"),
                                target_line=base_attrs.get("start_line"),
                                detection_method="ast_inheritance",
                                certainty=RelationshipCertainty.CONFIRMED,
                                evidence=f"Class '{entity.name}' inherits from base class '{base_name}'",
                                metadata={"subclass": entity.name, "base_class": base_name},
                            )
                        else:
                            if not base_name.startswith(("BaseModel", "object", "Exception", "TestCase", "Enum", "ABC", "dict", "list", "tuple")):
                                self._limitations.append(
                                    f"Unresolved base class '{base_name}' for '{entity.name}' in '{file_path}'"
                                )

        # 6. Add TESTS Edges (Linking Tests to Exercised Entities)
        for file_path, pr_result in parse_results.items():
            if not pr_result:
                continue
            norm_file = file_path.replace("\\", "/")
            is_test_file = (
                norm_file.startswith("tests/")
                or norm_file.startswith("test/")
                or "/tests/" in norm_file
                or "test_" in norm_file
                or norm_file.endswith("_test.py")
            )
            if not is_test_file:
                continue

            test_file_node = f"file:{file_path}"
            for call in pr_result.call_sites or []:
                callee_node_id, call_certainty = self._resolve_call_with_certainty(call, file_path, pr_result)
                if callee_node_id and self._graph.has_node(callee_node_id):
                    caller_node_id = (
                        f"entity:{call.caller_entity_id}"
                        if call.caller_entity_id and self._graph.has_node(f"entity:{call.caller_entity_id}")
                        else test_file_node
                    )
                    # Add TESTS edge if not already pointing there
                    if not self._graph.has_edge(caller_node_id, callee_node_id):
                        callee_attrs = self._graph.nodes.get(callee_node_id, {})
                        self._graph.add_edge(
                            caller_node_id,
                            callee_node_id,
                            edge_type=EdgeType.TESTS,
                            source_file=file_path,
                            source_line=call.line_number,
                            target_file=callee_attrs.get("file_path"),
                            target_line=callee_attrs.get("start_line"),
                            detection_method="ast_test_invocation",
                            certainty=call_certainty,
                            evidence=f"Test case exercises '{call.callee_name}'",
                            metadata={"test_caller": caller_node_id, "exercised_symbol": call.callee_name},
                        )

    def compute_impact(
        self,
        changed_entity_ids: List[str],
        max_depth: int = 5,
    ) -> ChangeGraphReport:
        """Traverse the dependency graph to find downstream entities and files impacted by changes.

        For each changed entity, downstream impact propagates through:
        - Callers: entities that invoke the changed entity (reverse CALLS edge)
        - Subclasses: classes that inherit from the changed class (reverse INHERITS edge)
        - Tests: test cases exercising the changed entity (reverse TESTS edge)
        - Importers: files/modules that import the changed file or entity (reverse IMPORTS edge)

        Args:
            changed_entity_ids: IDs of directly modified entities or files.
            max_depth: Maximum hops for transitive impact propagation.

        Returns:
            ChangeGraphReport containing impacted entities, impacted files, and explainable paths.
        """
        # Normalize changed entity IDs to graph node format
        target_changed_nodes: Set[str] = set()
        for raw_id in changed_entity_ids:
            if not raw_id:
                continue
            if raw_id.startswith(("file:", "entity:")) and self._graph.has_node(raw_id):
                target_changed_nodes.add(raw_id)
            elif f"entity:{raw_id}" in self._graph:
                target_changed_nodes.add(f"entity:{raw_id}")
            elif f"file:{raw_id}" in self._graph:
                target_changed_nodes.add(f"file:{raw_id}")
            elif raw_id in self._entity_lookup:
                target_changed_nodes.add(self._entity_lookup[raw_id])
            else:
                self._limitations.append(
                    f"Changed entity '{raw_id}' does not match any node in the AST dependency graph."
                )

        if not target_changed_nodes:
            return ChangeGraphReport(
                total_nodes=self._graph.number_of_nodes(),
                total_edges=self._graph.number_of_edges(),
                changed_entities=list(target_changed_nodes),
                impacted_entities_count=0,
                impacted_files_count=0,
                direct_impacted_entities_count=0,
                transitive_impacted_entities_count=0,
                direct_impacted_files_count=0,
                transitive_impacted_files_count=0,
                impacted_entities=[],
                impacted_files=[],
                graph_limitations=list(set(self._limitations)),
                edges=self._collect_graph_edges(),
            )

        # Track directly changed files
        changed_files_set: Set[str] = {
            self._graph.nodes[n].get("file_path")
            for n in target_changed_nodes
            if n in self._graph and self._graph.nodes[n].get("file_path")
        }

        # BFS downstream impact tracking
        # Map: impacted_node_id -> list of ImpactPath
        impact_paths_by_node: Dict[str, List[ImpactPath]] = {}
        min_distance_by_node: Dict[str, int] = {}
        seen_path_keys_by_node: Dict[str, Set[Tuple[str, ...]]] = {}

        for changed_node in target_changed_nodes:
            changed_name = self._get_node_label(changed_node)

            # Queue elements: (current_node, distance, path_nodes, path_steps)
            queue = deque([(changed_node, 0, [changed_node], [changed_name])])
            visited_per_source: Set[str] = {changed_node}

            while queue:
                current_node, dist, path_nodes, path_steps = queue.popleft()

                if dist >= max_depth:
                    continue

                for predecessor in self._graph.predecessors(current_node):
                    edge_data = self._graph.get_edge_data(predecessor, current_node) or {}
                    edge_type = edge_data.get("edge_type")
                    edge_certainty = edge_data.get("certainty", RelationshipCertainty.CONFIRMED)

                    # Do NOT treat enclosing file as a downstream caller of its own modified entity
                    if edge_type == EdgeType.CONTAINS:
                        continue

                    # Do not loop back to the same changed entity
                    if predecessor in target_changed_nodes and predecessor == changed_node:
                        continue

                    pred_name = self._get_node_label(predecessor)
                    if edge_type == EdgeType.CALLS:
                        step_str = f"called by {pred_name}"
                        reason = f"Calls changed entity '{changed_name}'"
                    elif edge_type == EdgeType.IMPORTS:
                        step_str = f"imported by {pred_name}"
                        reason = f"Imports changed module/entity '{changed_name}'"
                    elif edge_type == EdgeType.INHERITS:
                        step_str = f"subclass {pred_name}"
                        reason = f"Inherits from changed class '{changed_name}'"
                    elif edge_type == EdgeType.TESTS:
                        step_str = f"tested by {pred_name}"
                        reason = f"Regression test exercising '{changed_name}'"
                    elif edge_type == EdgeType.REFERENCES:
                        step_str = f"referenced by {pred_name}"
                        reason = f"References changed symbol '{changed_name}'"
                    else:
                        step_str = f"linked to {pred_name}"
                        reason = f"Dependency connection to '{changed_name}'"

                    new_dist = dist + 1
                    new_path_nodes = list(path_nodes) + [predecessor]
                    new_path_steps = list(path_steps) + [step_str]
                    path_desc = " -> ".join(new_path_steps)

                    pred_attrs = self._graph.nodes.get(predecessor, {})
                    impact_path = ImpactPath(
                        target_id=predecessor,
                        target_name=pred_attrs.get("name", pred_name),
                        target_type=pred_attrs.get("node_type", NodeType.UNKNOWN),
                        target_file=pred_attrs.get("file_path", ""),
                        path_nodes=new_path_nodes,
                        path_description=path_desc,
                        distance=new_dist,
                        impact_reason=reason,
                        certainty=edge_certainty,
                        origin_changed_entity=changed_node,
                    )

                    if predecessor not in impact_paths_by_node:
                        impact_paths_by_node[predecessor] = []
                        min_distance_by_node[predecessor] = new_dist
                        seen_path_keys_by_node[predecessor] = set()

                    # Path deduplication
                    path_key = tuple(new_path_nodes)
                    if path_key not in seen_path_keys_by_node[predecessor]:
                        seen_path_keys_by_node[predecessor].add(path_key)
                        impact_paths_by_node[predecessor].append(impact_path)

                    min_distance_by_node[predecessor] = min(min_distance_by_node[predecessor], new_dist)

                    # Safe cycle prevention
                    if predecessor not in visited_per_source:
                        visited_per_source.add(predecessor)
                        queue.append((predecessor, new_dist, new_path_nodes, new_path_steps))

        # Build aggregated ImpactedEntity list & Impacted Files
        impacted_entities_list: List[ImpactedEntity] = []
        impacted_files_set: Set[str] = set()

        for node_id, paths in impact_paths_by_node.items():
            if node_id in target_changed_nodes:
                continue

            node_attrs = self._graph.nodes.get(node_id, {})
            node_type = node_attrs.get("node_type", NodeType.UNKNOWN)
            file_path = node_attrs.get("file_path", "")

            # Code entities (functions, methods, classes)
            if node_type in (NodeType.FUNCTION, NodeType.METHOD, NodeType.CLASS):
                min_dist = min_distance_by_node.get(node_id, 1)
                overall_certainty = (
                    RelationshipCertainty.CONFIRMED
                    if all(p.certainty == RelationshipCertainty.CONFIRMED for p in paths)
                    else RelationshipCertainty.INFERRED
                )

                impacted_entities_list.append(
                    ImpactedEntity(
                        node_id=node_id,
                        name=node_attrs.get("name", node_id),
                        entity_type=node_type,
                        file_path=file_path,
                        min_distance=min_dist,
                        certainty=overall_certainty,
                        impact_paths=paths,
                    )
                )
                if file_path:
                    impacted_files_set.add(file_path)

            elif node_type == NodeType.FILE:
                # File node (e.g. file importing modified module)
                if file_path and file_path not in changed_files_set:
                    impacted_files_set.add(file_path)

        # Sort entities: closest distance first, then name
        impacted_entities_list.sort(key=lambda x: (x.min_distance, x.name))

        # Direct vs Transitive Breakdown
        direct_entities_count = sum(1 for e in impacted_entities_list if e.min_distance == 1)
        transitive_entities_count = sum(1 for e in impacted_entities_list if e.min_distance > 1)

        direct_files: Set[str] = set()
        for e in impacted_entities_list:
            if e.min_distance == 1 and e.file_path:
                direct_files.add(e.file_path)
        for node_id, paths in impact_paths_by_node.items():
            if node_id.startswith("file:") and min_distance_by_node.get(node_id) == 1:
                f_path = self._graph.nodes.get(node_id, {}).get("file_path")
                if f_path and f_path not in changed_files_set:
                    direct_files.add(f_path)

        transitive_files = impacted_files_set - direct_files

        return ChangeGraphReport(
            total_nodes=self._graph.number_of_nodes(),
            total_edges=self._graph.number_of_edges(),
            changed_entities=sorted(list(target_changed_nodes)),
            impacted_entities_count=len(impacted_entities_list),
            impacted_files_count=len(impacted_files_set),
            direct_impacted_entities_count=direct_entities_count,
            transitive_impacted_entities_count=transitive_entities_count,
            direct_impacted_files_count=len(direct_files),
            transitive_impacted_files_count=len(transitive_files),
            impacted_entities=impacted_entities_list,
            impacted_files=sorted(list(impacted_files_set)),
            graph_limitations=sorted(list(set(self._limitations))),
            edges=self._collect_graph_edges(),
        )

    def _collect_graph_edges(self) -> List[GraphEdge]:
        """Convert NetworkX graph edges into structured GraphEdge models."""
        edges: List[GraphEdge] = []
        for u, v, data in self._graph.edges(data=True):
            edges.append(
                GraphEdge(
                    source=u,
                    target=v,
                    edge_type=data.get("edge_type", EdgeType.CONTAINS),
                    source_file=data.get("source_file"),
                    source_line=data.get("source_line"),
                    target_file=data.get("target_file"),
                    target_line=data.get("target_line"),
                    detection_method=data.get("detection_method", "ast"),
                    certainty=data.get("certainty", RelationshipCertainty.CONFIRMED),
                    evidence=data.get("evidence", ""),
                    metadata=data.get("metadata", {}),
                )
            )
        return edges

    # -------------------------------------------------------------------------
    # Helper resolution methods
    # -------------------------------------------------------------------------

    def _resolve_import(
        self,
        imp: ImportEntity,
        parse_results: Dict[str, Optional[ParseResult]],
    ) -> Optional[str]:
        """Resolve an import statement to a target File or Entity node."""
        mod_parts = imp.module.split(".")
        candidates = [
            "/".join(mod_parts) + ".py",
            "/".join(mod_parts) + "/__init__.py",
            mod_parts[-1] + ".py",
        ]

        # 1. Match imported file
        matched_file = None
        for cand in candidates:
            for file_path in parse_results.keys():
                normalized = file_path.replace("\\", "/")
                if normalized.endswith(cand) or normalized == cand:
                    matched_file = file_path
                    break
            if matched_file:
                break

        if not matched_file:
            return None

        # 2. If specific symbol is imported (e.g. from app.billing import BillingService)
        if imp.name:
            target_entity_id = self._entity_lookup.get(f"{matched_file}#{imp.name}")
            if target_entity_id and self._graph.has_node(target_entity_id):
                return target_entity_id

        # 3. Fallback to imported file node
        file_node_id = f"file:{matched_file}"
        if self._graph.has_node(file_node_id):
            return file_node_id

        return None

    def _resolve_call_with_certainty(
        self,
        call: CallSite,
        caller_file: str,
        parse_result: ParseResult,
    ) -> Tuple[Optional[str], RelationshipCertainty]:
        """Resolve a function or method invocation with confidence level."""
        callee = call.callee_name

        if callee.startswith("self."):
            callee_symbol = callee[5:]
        elif callee.startswith("cls."):
            callee_symbol = callee[4:]
        else:
            callee_symbol = callee

        # A. Same file resolution -> CONFIRMED
        same_file_key = f"{caller_file}#{callee_symbol}"
        if same_file_key in self._entity_lookup:
            return self._entity_lookup[same_file_key], RelationshipCertainty.CONFIRMED

        # B. Check if callee is imported symbol -> CONFIRMED
        for imp in parse_result.imports:
            symbol_name = imp.alias or imp.name or imp.module.split(".")[-1]
            if symbol_name == callee_symbol or callee.startswith(f"{symbol_name}."):
                resolved_target = self._resolve_import(imp, {caller_file: parse_result})
                if resolved_target:
                    if resolved_target.startswith("entity:"):
                        return resolved_target, RelationshipCertainty.CONFIRMED
                    if "." in callee:
                        attr_name = callee.split(".")[-1]
                        target_file = resolved_target.replace("file:", "")
                        ent_key = f"{target_file}#{attr_name}"
                        if ent_key in self._entity_lookup:
                            return self._entity_lookup[ent_key], RelationshipCertainty.CONFIRMED

        # C. Global entity lookup fallback by symbol name -> INFERRED
        if callee_symbol in self._entity_lookup:
            return self._entity_lookup[callee_symbol], RelationshipCertainty.INFERRED

        return None, RelationshipCertainty.UNKNOWN

    def _resolve_call(
        self,
        call: CallSite,
        caller_file: str,
        parse_result: ParseResult,
    ) -> Optional[str]:
        """Backward-compatible helper returning target node ID."""
        target, _ = self._resolve_call_with_certainty(call, caller_file, parse_result)
        return target

    def _resolve_class_inheritance(
        self,
        base_name: str,
        caller_file: str,
        parse_result: ParseResult,
    ) -> Optional[str]:
        """Resolve a class superclass to an entity node ID."""
        # 1. Same file
        same_file_key = f"{caller_file}#{base_name}"
        if same_file_key in self._entity_lookup:
            return self._entity_lookup[same_file_key]

        # 2. Via imports
        for imp in parse_result.imports:
            symbol_name = imp.alias or imp.name or imp.module.split(".")[-1]
            if symbol_name == base_name or base_name.startswith(f"{symbol_name}."):
                resolved = self._resolve_import(imp, {caller_file: parse_result})
                if resolved and resolved.startswith("entity:"):
                    return resolved
                if "." in base_name and resolved and resolved.startswith("file:"):
                    attr_name = base_name.split(".")[-1]
                    target_file = resolved.replace("file:", "")
                    ent_key = f"{target_file}#{attr_name}"
                    if ent_key in self._entity_lookup:
                        return self._entity_lookup[ent_key]

        # 3. Global lookup fallback
        if base_name in self._entity_lookup:
            return self._entity_lookup[base_name]

        return None

    def _get_node_label(self, node_id: str) -> str:
        """Returns clean short label for a node in human-readable path traces."""
        if self._graph.has_node(node_id):
            attrs = self._graph.nodes[node_id]
            file_path = attrs.get("file_path", "")
            name = attrs.get("name", node_id)
            if node_id.startswith("file:"):
                return file_path
            return f"{file_path}::{name}"
        return node_id

    @staticmethod
    def _map_entity_type(ent_type: CodeEntityType) -> NodeType:
        if ent_type == CodeEntityType.CLASS:
            return NodeType.CLASS
        elif ent_type == CodeEntityType.FUNCTION:
            return NodeType.FUNCTION
        elif ent_type == CodeEntityType.METHOD:
            return NodeType.METHOD
        return NodeType.UNKNOWN
