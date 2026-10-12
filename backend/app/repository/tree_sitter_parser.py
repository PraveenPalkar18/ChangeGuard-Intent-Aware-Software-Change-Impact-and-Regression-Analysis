"""Tree-sitter based source code parser for Python."""
from typing import List, Optional, Tuple
import tree_sitter_python as tspython
from tree_sitter import Language as TSLanguage, Parser, Node

from backend.app.repository.parser_interface import BaseCodeParser
from backend.app.repository.models import (
    CodeEntity,
    CodeEntityType,
    ImportEntity,
    CallSite,
    ParseErrorNode,
    ParseResult,
)

# Initialize tree-sitter Python language and parser instance
PY_LANGUAGE = TSLanguage(tspython.language())


class TreeSitterPythonParser(BaseCodeParser):
    """Python AST parser implemented with Tree-sitter."""

    def __init__(self):
        self._parser = Parser(PY_LANGUAGE)

    def supports_language(self, language: str) -> bool:
        """Returns True if the target file/language is Python."""
        normalized = language.strip().lower()
        return normalized in ("python", "py") or normalized.endswith(".py")

    def parse_source(self, file_path: str, source_code: str) -> ParseResult:
        """Parse Python source code and extract code entities, imports, and calls.

        Handles syntax errors gracefully, preserving partial entities.
        """
        if not self.supports_language(file_path):
            return ParseResult(
                file_path=file_path,
                language="unsupported",
                is_success=False,
                error_message=f"Unsupported language for TreeSitterPythonParser on file: '{file_path}'",
            )

        raw_loc = len(source_code.splitlines()) if source_code else 0
        if not source_code or not source_code.strip():
            # Empty or whitespace-only file is valid Python
            return ParseResult(
                file_path=file_path,
                language="python",
                is_success=True,
                has_syntax_errors=False,
                entities=[],
                imports=[],
                call_sites=[],
                error_nodes=[],
                raw_loc=raw_loc,
            )

        source_bytes = source_code.encode("utf-8")
        try:
            tree = self._parser.parse(source_bytes)
        except Exception as exc:
            return ParseResult(
                file_path=file_path,
                language="python",
                is_success=False,
                error_message=f"Tree-sitter parser exception: {str(exc)}",
                raw_loc=raw_loc,
            )

        root = tree.root_node
        has_syntax_errors = root.has_error

        # Collect error nodes if any
        error_nodes: List[ParseErrorNode] = []
        if has_syntax_errors:
            self._collect_error_nodes(root, error_nodes)

        entities: List[CodeEntity] = []
        imports: List[ImportEntity] = []
        call_sites: List[CallSite] = []

        # Walk AST to extract entities, imports, and call sites
        self._traverse_node(
            node=root,
            file_path=file_path,
            parent_entity=None,
            caller_id=None,
            entities=entities,
            imports=imports,
            call_sites=call_sites,
        )

        return ParseResult(
            file_path=file_path,
            language="python",
            is_success=True,
            has_syntax_errors=has_syntax_errors,
            entities=entities,
            imports=imports,
            call_sites=call_sites,
            error_nodes=error_nodes,
            raw_loc=raw_loc,
        )

    def _collect_error_nodes(self, node: Node, error_nodes: List[ParseErrorNode]):
        """Recursively collect syntax error and missing nodes."""
        is_err = getattr(node, "is_error", False) or node.type == "ERROR"
        is_missing = getattr(node, "is_missing", False)

        if is_err or is_missing:
            start_l = node.start_point.row + 1
            end_l = node.end_point.row + 1
            text = node.text.decode("utf-8", errors="ignore") if node.text else "(missing syntax)"
            error_nodes.append(
                ParseErrorNode(
                    start_line=start_l,
                    end_line=end_l,
                    error_text=text[:100],  # Truncate long snippets
                )
            )
            return

        for child in node.children:
            if child.has_error:
                self._collect_error_nodes(child, error_nodes)

    def _traverse_node(
        self,
        node: Node,
        file_path: str,
        parent_entity: Optional[CodeEntity],
        caller_id: Optional[str],
        entities: List[CodeEntity],
        imports: List[ImportEntity],
        call_sites: List[CallSite],
    ):
        """Recursive visitor tracking context, enclosing entities, and call sites."""
        node_type = node.type

        # 1. Imports
        if node_type == "import_statement":
            self._extract_import_statement(node, imports)
            return
        elif node_type == "import_from_statement":
            self._extract_import_from_statement(node, imports)
            return

        # 2. Call Sites
        if node_type == "call":
            self._extract_call_site(node, caller_id, call_sites)
            # Continue traversal inside call to capture nested calls e.g. f(g())
            for child in node.children:
                self._traverse_node(
                    node=child,
                    file_path=file_path,
                    parent_entity=parent_entity,
                    caller_id=caller_id,
                    entities=entities,
                    imports=imports,
                    call_sites=call_sites,
                )
            return

        # 3. Class or Function with Decorator wrapper
        if node_type == "decorated_definition":
            decorators = []
            def_node = None
            for child in node.children:
                if child.type == "decorator":
                    decorators.append(child.text.decode("utf-8", errors="ignore").strip())
                elif child.type in ("function_definition", "class_definition"):
                    def_node = child

            if def_node:
                self._process_definition(
                    def_node=def_node,
                    outer_node=node,
                    decorators=decorators,
                    file_path=file_path,
                    parent_entity=parent_entity,
                    entities=entities,
                    imports=imports,
                    call_sites=call_sites,
                )
            return

        # 4. Standard Function or Class Definition (undecorated)
        if node_type in ("function_definition", "class_definition"):
            self._process_definition(
                def_node=node,
                outer_node=node,
                decorators=[],
                file_path=file_path,
                parent_entity=parent_entity,
                entities=entities,
                imports=imports,
                call_sites=call_sites,
            )
            return

        # General traversal
        for child in node.children:
            self._traverse_node(
                node=child,
                file_path=file_path,
                parent_entity=parent_entity,
                caller_id=caller_id,
                entities=entities,
                imports=imports,
                call_sites=call_sites,
            )

    def _process_definition(
        self,
        def_node: Node,
        outer_node: Node,
        decorators: List[str],
        file_path: str,
        parent_entity: Optional[CodeEntity],
        entities: List[CodeEntity],
        imports: List[ImportEntity],
        call_sites: List[CallSite],
    ):
        """Process a class or function definition and traverse its body."""
        name_node = def_node.child_by_field_name("name")
        if not name_node or not name_node.text:
            return

        name = name_node.text.decode("utf-8", errors="ignore").strip()
        start_line = outer_node.start_point.row + 1
        end_line = outer_node.end_point.row + 1

        # Determine entity type, nesting, and identifier
        if def_node.type == "class_definition":
            entity_type = CodeEntityType.CLASS
            if parent_entity is None:
                entity_id = f"{file_path}::{name}"
            else:
                entity_id = f"{parent_entity.id}.{name}"
            is_async = False
            params = []
        else:
            # function_definition
            is_method = parent_entity is not None and parent_entity.entity_type == CodeEntityType.CLASS
            entity_type = CodeEntityType.METHOD if is_method else CodeEntityType.FUNCTION

            if parent_entity is None:
                entity_id = f"{file_path}::{name}"
            else:
                entity_id = f"{parent_entity.id}.{name}"

            # Check async
            is_async = any(c.type == "async" for c in def_node.children)

            # Parameters
            params = []
            params_node = def_node.child_by_field_name("parameters")
            if params_node:
                for p in params_node.children:
                    if p.type in ("(", ")", ","):
                        continue
                    p_text = p.text.decode("utf-8", errors="ignore").strip()
                    # Clean type hints or default values
                    if ":" in p_text:
                        p_name = p_text.split(":")[0].strip()
                    elif "=" in p_text:
                        p_name = p_text.split("=")[0].strip()
                    else:
                        p_name = p_text
                    if p_name:
                        params.append(p_name)

        # Extract docstring if present
        docstring = self._extract_docstring(def_node)

        entity = CodeEntity(
            id=entity_id,
            name=name,
            entity_type=entity_type,
            file_path=file_path,
            start_line=start_line,
            end_line=end_line,
            parent_id=parent_entity.id if parent_entity else None,
            docstring=docstring,
            parameters=params,
            decorators=decorators,
            is_async=is_async,
        )
        entities.append(entity)

        # Traverse body with this entity as the enclosing context
        body_node = def_node.child_by_field_name("body")
        if body_node:
            for child in body_node.children:
                self._traverse_node(
                    node=child,
                    file_path=file_path,
                    parent_entity=entity,
                    caller_id=entity.id if entity.entity_type in (CodeEntityType.FUNCTION, CodeEntityType.METHOD) else None,
                    entities=entities,
                    imports=imports,
                    call_sites=call_sites,
                )

    def _extract_docstring(self, def_node: Node) -> Optional[str]:
        """Extract leading docstring literal from function or class body."""
        body = def_node.child_by_field_name("body")
        if not body:
            return None

        for child in body.children:
            if child.type == "expression_statement":
                for sub in child.children:
                    if sub.type == "string":
                        raw = sub.text.decode("utf-8", errors="ignore").strip()
                        # Strip triple quotes or single quotes
                        for quote in ('"""', "'''", '"', "'"):
                            if raw.startswith(quote) and raw.endswith(quote):
                                return raw[len(quote):-len(quote)].strip()
                        return raw.strip()
            # If first statement is not docstring, stop looking
            if child.type not in ("comment",):
                break
        return None

    def _extract_import_statement(self, node: Node, imports: List[ImportEntity]):
        """Extract 'import x', 'import x as y', 'import x, y'."""
        line_num = node.start_point.row + 1
        for child in node.children:
            if child.type == "dotted_name":
                mod_name = child.text.decode("utf-8", errors="ignore").strip()
                imports.append(
                    ImportEntity(
                        module=mod_name,
                        name=None,
                        alias=None,
                        line_number=line_num,
                        is_from_import=False,
                    )
                )
            elif child.type == "aliased_import":
                orig = child.child_by_field_name("name")
                alias = child.child_by_field_name("alias")
                mod_name = orig.text.decode("utf-8", errors="ignore").strip() if orig else ""
                alias_name = alias.text.decode("utf-8", errors="ignore").strip() if alias else None
                if mod_name:
                    imports.append(
                        ImportEntity(
                            module=mod_name,
                            name=None,
                            alias=alias_name,
                            line_number=line_num,
                            is_from_import=False,
                        )
                    )

    def _extract_import_from_statement(self, node: Node, imports: List[ImportEntity]):
        """Extract 'from x import y', 'from x import y as z'."""
        line_num = node.start_point.row + 1
        module_name = ""

        # Find module name before 'import' keyword
        has_reached_import = False
        import_symbols = []

        for child in node.children:
            if child.type == "import":
                has_reached_import = True
                continue

            if not has_reached_import:
                if child.type in ("dotted_name", "relative_import"):
                    part = child.text.decode("utf-8", errors="ignore").strip()
                    module_name = f"{module_name}{part}" if module_name else part
            else:
                if child.type in ("dotted_name", "aliased_import", "wildcard_import"):
                    import_symbols.append(child)

        for sym in import_symbols:
            if sym.type == "dotted_name":
                s_name = sym.text.decode("utf-8", errors="ignore").strip()
                imports.append(
                    ImportEntity(
                        module=module_name,
                        name=s_name,
                        alias=None,
                        line_number=line_num,
                        is_from_import=True,
                    )
                )
            elif sym.type == "aliased_import":
                orig = sym.child_by_field_name("name")
                alias = sym.child_by_field_name("alias")
                s_name = orig.text.decode("utf-8", errors="ignore").strip() if orig else ""
                alias_name = alias.text.decode("utf-8", errors="ignore").strip() if alias else None
                imports.append(
                    ImportEntity(
                        module=module_name,
                        name=s_name,
                        alias=alias_name,
                        line_number=line_num,
                        is_from_import=True,
                    )
                )
            elif sym.type == "wildcard_import":
                imports.append(
                    ImportEntity(
                        module=module_name,
                        name="*",
                        alias=None,
                        line_number=line_num,
                        is_from_import=True,
                    )
                )

    def _extract_call_site(self, node: Node, caller_id: Optional[str], call_sites: List[CallSite]):
        """Extract function/method invocation details."""
        fn_node = node.child_by_field_name("function")
        if not fn_node:
            return

        callee_name = fn_node.text.decode("utf-8", errors="ignore").strip()
        line_num = node.start_point.row + 1

        args_count = 0
        args_node = node.child_by_field_name("arguments")
        if args_node:
            args_count = len([c for c in args_node.children if c.type not in ("(", ")", ",")])

        call_sites.append(
            CallSite(
                caller_entity_id=caller_id,
                callee_name=callee_name,
                line_number=line_num,
                arguments_count=args_count,
            )
        )
