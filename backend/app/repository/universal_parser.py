"""Universal multi-language source code parser for ChangeGuard.

Supports:
- Python (.py)
- JavaScript (.js, .jsx, .mjs, .cjs)
- TypeScript (.ts, .tsx)
- Go (.go)
- Java (.java)
- Rust (.rs)
- C# (.cs)
- Universal heuristic / regex fallback for all other languages (.rb, .php, .kt, .swift, .cpp, .c, .scala, etc.)
"""
import os
import re
from typing import List, Optional, Tuple, Dict, Set
from tree_sitter import Language as TSLanguage, Parser, Node

# Tree-sitter language bindings
import tree_sitter_python as tspython
import tree_sitter_javascript as tsjs
import tree_sitter_typescript as tsts
import tree_sitter_go as tsgo
import tree_sitter_java as tsjava
import tree_sitter_rust as tsrust
import tree_sitter_c_sharp as tscs

from backend.app.repository.parser_interface import BaseCodeParser
from backend.app.repository.models import (
    CodeEntity,
    CodeEntityType,
    ImportEntity,
    CallSite,
    ParseErrorNode,
    ParseResult,
)
from backend.app.repository.tree_sitter_parser import TreeSitterPythonParser

# Ignored binary/media extensions
IGNORED_EXTENSIONS = {
    ".png", ".jpg", ".jpeg", ".gif", ".ico", ".svg", ".webp",
    ".woff", ".woff2", ".ttf", ".eot", ".otf",
    ".zip", ".tar", ".gz", ".7z", ".rar",
    ".pdf", ".exe", ".dll", ".so", ".dylib", ".bin",
    ".lock", ".map", ".min.js", ".min.css",
}


class UniversalCodeParser(BaseCodeParser):
    """Universal parser that routes to high-precision Tree-sitter grammars or heuristic fallback."""

    def __init__(self):
        # 1. Python parser (existing battle-tested implementation)
        self._python_parser = TreeSitterPythonParser()

        # 2. Tree-sitter parsers for other major languages
        self._js_lang = TSLanguage(tsjs.language())
        self._js_parser = Parser(self._js_lang)

        self._ts_lang = TSLanguage(tsts.language_typescript())
        self._ts_parser = Parser(self._ts_lang)

        self._go_lang = TSLanguage(tsgo.language())
        self._go_parser = Parser(self._go_lang)

        self._java_lang = TSLanguage(tsjava.language())
        self._java_parser = Parser(self._java_lang)

        self._rust_lang = TSLanguage(tsrust.language())
        self._rust_parser = Parser(self._rust_lang)

        self._csharp_lang = TSLanguage(tscs.language())
        self._csharp_parser = Parser(self._csharp_lang)

    CODE_EXTENSIONS = {
        ".py", ".pyw", ".pyi",
        ".js", ".jsx", ".mjs", ".cjs",
        ".ts", ".tsx",
        ".go",
        ".java",
        ".rs",
        ".cs",
        ".c", ".cpp", ".cc", ".cxx", ".h", ".hpp",
        ".rb", ".php", ".kt", ".kts", ".swift", ".scala", ".dart", ".sh", ".bash",
    }

    def supports_language(self, language_or_file: str) -> bool:
        """Returns True for recognized source code files."""
        if not language_or_file:
            return False
        normalized = language_or_file.strip().lower()
        ext = os.path.splitext(normalized)[1]
        if ext in self.CODE_EXTENSIONS:
            return True
        return normalized in ("python", "py", "javascript", "js", "typescript", "ts", "go", "java", "rust", "csharp")

    def detect_language(self, file_path: str) -> str:
        """Identify language from file extension."""
        ext = os.path.splitext(file_path.lower())[1]
        if ext in (".py", ".pyw", ".pyi"):
            return "python"
        elif ext in (".js", ".jsx", ".mjs", ".cjs"):
            return "javascript"
        elif ext in (".ts", ".tsx"):
            return "typescript"
        elif ext == ".go":
            return "go"
        elif ext == ".java":
            return "java"
        elif ext == ".rs":
            return "rust"
        elif ext == ".cs":
            return "csharp"
        else:
            return "generic"

    def parse_source(self, file_path: str, source_code: str) -> ParseResult:
        """Parse source code for any supported programming language."""
        if not self.supports_language(file_path):
            return ParseResult(
                file_path=file_path,
                language="unsupported",
                is_success=False,
                error_message=f"Ignored or binary file extension: '{file_path}'",
            )

        lang = self.detect_language(file_path)

        if lang == "python":
            return self._python_parser.parse_source(file_path, source_code)
        elif lang in ("javascript", "typescript"):
            parser = self._ts_parser if lang == "typescript" else self._js_parser
            return self._parse_js_ts(file_path, source_code, lang, parser)
        elif lang == "go":
            return self._parse_go(file_path, source_code)
        elif lang == "java":
            return self._parse_java(file_path, source_code)
        elif lang == "rust":
            return self._parse_rust(file_path, source_code)
        elif lang == "csharp":
            return self._parse_csharp(file_path, source_code)
        else:
            # Universal regex heuristic fallback for any other language
            return self._parse_generic_heuristic(file_path, source_code)

    # -------------------------------------------------------------------------
    # JavaScript & TypeScript Tree-sitter Parser
    # -------------------------------------------------------------------------
    def _parse_js_ts(self, file_path: str, source_code: str, language: str, parser: Parser) -> ParseResult:
        raw_loc = len(source_code.splitlines()) if source_code else 0
        if not source_code or not source_code.strip():
            return ParseResult(
                file_path=file_path, language=language, is_success=True, raw_loc=raw_loc
            )

        try:
            tree = parser.parse(source_code.encode("utf-8"))
        except Exception as exc:
            return ParseResult(
                file_path=file_path, language=language, is_success=False, error_message=str(exc), raw_loc=raw_loc
            )

        root = tree.root_node
        entities: List[CodeEntity] = []
        imports: List[ImportEntity] = []
        call_sites: List[CallSite] = []
        error_nodes: List[ParseErrorNode] = []

        if root.has_error:
            self._collect_error_nodes(root, error_nodes)

        self._walk_js(root, file_path, None, None, entities, imports, call_sites)

        return ParseResult(
            file_path=file_path,
            language=language,
            is_success=True,
            has_syntax_errors=root.has_error,
            entities=entities,
            imports=imports,
            call_sites=call_sites,
            error_nodes=error_nodes,
            raw_loc=raw_loc,
        )

    def _walk_js(
        self,
        node: Node,
        file_path: str,
        parent: Optional[CodeEntity],
        caller_id: Optional[str],
        entities: List[CodeEntity],
        imports: List[ImportEntity],
        call_sites: List[CallSite],
    ):
        ntype = node.type

        # 1. ES Import
        if ntype == "import_statement":
            line = node.start_point.row + 1
            src_node = node.child_by_field_name("source")
            mod_name = src_node.text.decode("utf-8", errors="ignore").strip("'\"") if src_node else ""
            imports.append(ImportEntity(module=mod_name, line_number=line, is_from_import=True))
            return

        # 2. CommonJS require or variable assigned functions
        if ntype in ("lexical_declaration", "variable_declaration"):
            line = node.start_point.row + 1
            for child in node.children:
                if child.type == "variable_declarator":
                    name_node = child.child_by_field_name("name")
                    val_node = child.child_by_field_name("value")

                    # CommonJS require(...)
                    if val_node and val_node.type == "call_expression":
                        fn_n = val_node.child_by_field_name("function")
                        if fn_n and fn_n.text.decode("utf-8", errors="ignore") == "require":
                            args_n = val_node.child_by_field_name("arguments")
                            mod_name = ""
                            if args_n and len(args_n.children) > 1:
                                mod_name = args_n.children[1].text.decode("utf-8", errors="ignore").strip("'\"")
                            sym_name = name_node.text.decode("utf-8", errors="ignore").strip() if name_node else None
                            imports.append(ImportEntity(module=mod_name, name=sym_name, line_number=line, is_from_import=True))
                            continue

                    # Arrow function or function expression
                    if val_node and val_node.type in ("arrow_function", "function_expression"):
                        fn_name = name_node.text.decode("utf-8", errors="ignore").strip() if name_node else "anonymous"
                        ent_id = f"{file_path}::{fn_name}" if not parent else f"{parent.id}.{fn_name}"
                        ent = CodeEntity(
                            id=ent_id,
                            name=fn_name,
                            entity_type=CodeEntityType.FUNCTION,
                            file_path=file_path,
                            start_line=node.start_point.row + 1,
                            end_line=node.end_point.row + 1,
                            parent_id=parent.id if parent else None,
                        )
                        entities.append(ent)
                        self._walk_js(val_node, file_path, ent, ent.id, entities, imports, call_sites)
                        continue

        # 3. Class declaration
        if ntype == "class_declaration":
            name_node = node.child_by_field_name("name")
            c_name = name_node.text.decode("utf-8", errors="ignore").strip() if name_node else "AnonymousClass"
            ent_id = f"{file_path}::{c_name}" if not parent else f"{parent.id}.{c_name}"
            ent = CodeEntity(
                id=ent_id,
                name=c_name,
                entity_type=CodeEntityType.CLASS,
                file_path=file_path,
                start_line=node.start_point.row + 1,
                end_line=node.end_point.row + 1,
                parent_id=parent.id if parent else None,
            )
            entities.append(ent)
            body = node.child_by_field_name("body")
            if body:
                for child in body.children:
                    self._walk_js(child, file_path, ent, caller_id, entities, imports, call_sites)
            return

        # 4. Method definition inside class
        if ntype == "method_definition":
            name_node = node.child_by_field_name("name")
            m_name = name_node.text.decode("utf-8", errors="ignore").strip() if name_node else "anonymousMethod"
            ent_id = f"{parent.id}.{m_name}" if parent else f"{file_path}::{m_name}"
            ent = CodeEntity(
                id=ent_id,
                name=m_name,
                entity_type=CodeEntityType.METHOD,
                file_path=file_path,
                start_line=node.start_point.row + 1,
                end_line=node.end_point.row + 1,
                parent_id=parent.id if parent else None,
            )
            entities.append(ent)
            body = node.child_by_field_name("body")
            if body:
                for child in body.children:
                    self._walk_js(child, file_path, ent, ent.id, entities, imports, call_sites)
            return

        # 5. Function declaration
        if ntype in ("function_declaration", "generator_function_declaration"):
            name_node = node.child_by_field_name("name")
            f_name = name_node.text.decode("utf-8", errors="ignore").strip() if name_node else "anonymous"
            ent_id = f"{file_path}::{f_name}" if not parent else f"{parent.id}.{f_name}"
            ent = CodeEntity(
                id=ent_id,
                name=f_name,
                entity_type=CodeEntityType.FUNCTION,
                file_path=file_path,
                start_line=node.start_point.row + 1,
                end_line=node.end_point.row + 1,
                parent_id=parent.id if parent else None,
            )
            entities.append(ent)
            body = node.child_by_field_name("body")
            if body:
                for child in body.children:
                    self._walk_js(child, file_path, ent, ent.id, entities, imports, call_sites)
            return

        # 6. Call expression
        if ntype == "call_expression":
            fn_node = node.child_by_field_name("function")
            if fn_node:
                callee = fn_node.text.decode("utf-8", errors="ignore").strip()
                if callee != "require":
                    line = node.start_point.row + 1
                    # Strip prefixes if member expression
                    if "." in callee:
                        callee = callee.split(".")[-1]
                    call_sites.append(CallSite(caller_entity_id=caller_id, callee_name=callee, line_number=line))

        # Children traversal
        for child in node.children:
            self._walk_js(child, file_path, parent, caller_id, entities, imports, call_sites)

    # -------------------------------------------------------------------------
    # Go Tree-sitter Parser
    # -------------------------------------------------------------------------
    def _parse_go(self, file_path: str, source_code: str) -> ParseResult:
        raw_loc = len(source_code.splitlines()) if source_code else 0
        if not source_code or not source_code.strip():
            return ParseResult(file_path=file_path, language="go", is_success=True, raw_loc=raw_loc)

        try:
            tree = self._go_parser.parse(source_code.encode("utf-8"))
        except Exception as exc:
            return ParseResult(file_path=file_path, language="go", is_success=False, error_message=str(exc), raw_loc=raw_loc)

        root = tree.root_node
        entities: List[CodeEntity] = []
        imports: List[ImportEntity] = []
        call_sites: List[CallSite] = []
        error_nodes: List[ParseErrorNode] = []

        if root.has_error:
            self._collect_error_nodes(root, error_nodes)

        self._walk_go(root, file_path, None, entities, imports, call_sites)

        return ParseResult(
            file_path=file_path,
            language="go",
            is_success=True,
            has_syntax_errors=root.has_error,
            entities=entities,
            imports=imports,
            call_sites=call_sites,
            error_nodes=error_nodes,
            raw_loc=raw_loc,
        )

    def _walk_go(self, node: Node, file_path: str, caller_id: Optional[str],
                 entities: List[CodeEntity], imports: List[ImportEntity], call_sites: List[CallSite]):
        ntype = node.type

        # Imports
        if ntype == "import_spec":
            line = node.start_point.row + 1
            path_n = node.child_by_field_name("path")
            mod_name = path_n.text.decode("utf-8", errors="ignore").strip('"') if path_n else ""
            imports.append(ImportEntity(module=mod_name, line_number=line, is_from_import=True))
            return

        # Type struct / interface (Class equivalent)
        if ntype == "type_spec":
            name_n = node.child_by_field_name("name")
            t_name = name_n.text.decode("utf-8", errors="ignore").strip() if name_n else "Type"
            ent_id = f"{file_path}::{t_name}"
            entities.append(CodeEntity(
                id=ent_id,
                name=t_name,
                entity_type=CodeEntityType.CLASS,
                file_path=file_path,
                start_line=node.start_point.row + 1,
                end_line=node.end_point.row + 1,
            ))

        # Function or Method
        if ntype in ("function_declaration", "method_declaration"):
            name_n = node.child_by_field_name("name")
            f_name = name_n.text.decode("utf-8", errors="ignore").strip() if name_n else "anonymous"
            receiver_n = node.child_by_field_name("receiver")
            if receiver_n and ntype == "method_declaration":
                # Method attached to receiver struct
                rec_text = receiver_n.text.decode("utf-8", errors="ignore").replace("*", "").replace("(", "").replace(")", "").split()
                rec_type = rec_text[-1] if rec_text else ""
                ent_id = f"{file_path}::{rec_type}.{f_name}" if rec_type else f"{file_path}::{f_name}"
                e_type = CodeEntityType.METHOD
            else:
                ent_id = f"{file_path}::{f_name}"
                e_type = CodeEntityType.FUNCTION

            ent = CodeEntity(
                id=ent_id,
                name=f_name,
                entity_type=e_type,
                file_path=file_path,
                start_line=node.start_point.row + 1,
                end_line=node.end_point.row + 1,
            )
            entities.append(ent)
            body = node.child_by_field_name("body")
            if body:
                for child in body.children:
                    self._walk_go(child, file_path, ent.id, entities, imports, call_sites)
            return

        # Calls
        if ntype == "call_expression":
            fn_n = node.child_by_field_name("function")
            if fn_n:
                callee = fn_n.text.decode("utf-8", errors="ignore").strip()
                if "." in callee:
                    callee = callee.split(".")[-1]
                call_sites.append(CallSite(caller_entity_id=caller_id, callee_name=callee, line_number=node.start_point.row + 1))

        for child in node.children:
            self._walk_go(child, file_path, caller_id, entities, imports, call_sites)

    # -------------------------------------------------------------------------
    # Java Tree-sitter Parser
    # -------------------------------------------------------------------------
    def _parse_java(self, file_path: str, source_code: str) -> ParseResult:
        raw_loc = len(source_code.splitlines()) if source_code else 0
        if not source_code or not source_code.strip():
            return ParseResult(file_path=file_path, language="java", is_success=True, raw_loc=raw_loc)

        try:
            tree = self._java_parser.parse(source_code.encode("utf-8"))
        except Exception as exc:
            return ParseResult(file_path=file_path, language="java", is_success=False, error_message=str(exc), raw_loc=raw_loc)

        root = tree.root_node
        entities: List[CodeEntity] = []
        imports: List[ImportEntity] = []
        call_sites: List[CallSite] = []
        error_nodes: List[ParseErrorNode] = []

        if root.has_error:
            self._collect_error_nodes(root, error_nodes)

        self._walk_java(root, file_path, None, None, entities, imports, call_sites)

        return ParseResult(
            file_path=file_path,
            language="java",
            is_success=True,
            has_syntax_errors=root.has_error,
            entities=entities,
            imports=imports,
            call_sites=call_sites,
            error_nodes=error_nodes,
            raw_loc=raw_loc,
        )

    def _walk_java(self, node: Node, file_path: str, parent: Optional[CodeEntity], caller_id: Optional[str],
                   entities: List[CodeEntity], imports: List[ImportEntity], call_sites: List[CallSite]):
        ntype = node.type

        # Import
        if ntype == "import_declaration":
            line = node.start_point.row + 1
            mod_text = node.text.decode("utf-8", errors="ignore").replace("import", "").replace("static", "").replace(";", "").strip()
            imports.append(ImportEntity(module=mod_text, line_number=line, is_from_import=True))
            return

        # Class / Interface
        if ntype in ("class_declaration", "interface_declaration", "enum_declaration"):
            name_n = node.child_by_field_name("name")
            c_name = name_n.text.decode("utf-8", errors="ignore").strip() if name_n else "Class"
            ent_id = f"{file_path}::{c_name}" if not parent else f"{parent.id}.{c_name}"
            ent = CodeEntity(
                id=ent_id,
                name=c_name,
                entity_type=CodeEntityType.CLASS,
                file_path=file_path,
                start_line=node.start_point.row + 1,
                end_line=node.end_point.row + 1,
                parent_id=parent.id if parent else None,
            )
            entities.append(ent)
            body = node.child_by_field_name("body")
            if body:
                for child in body.children:
                    self._walk_java(child, file_path, ent, caller_id, entities, imports, call_sites)
            return

        # Method / Constructor
        if ntype in ("method_declaration", "constructor_declaration"):
            name_n = node.child_by_field_name("name")
            m_name = name_n.text.decode("utf-8", errors="ignore").strip() if name_n else "method"
            ent_id = f"{parent.id}.{m_name}" if parent else f"{file_path}::{m_name}"
            ent = CodeEntity(
                id=ent_id,
                name=m_name,
                entity_type=CodeEntityType.METHOD,
                file_path=file_path,
                start_line=node.start_point.row + 1,
                end_line=node.end_point.row + 1,
                parent_id=parent.id if parent else None,
            )
            entities.append(ent)
            body = node.child_by_field_name("body")
            if body:
                for child in body.children:
                    self._walk_java(child, file_path, ent, ent.id, entities, imports, call_sites)
            return

        # Method Invocations
        if ntype == "method_invocation":
            name_n = node.child_by_field_name("name")
            if name_n:
                callee = name_n.text.decode("utf-8", errors="ignore").strip()
                call_sites.append(CallSite(caller_entity_id=caller_id, callee_name=callee, line_number=node.start_point.row + 1))

        for child in node.children:
            self._walk_java(child, file_path, parent, caller_id, entities, imports, call_sites)

    # -------------------------------------------------------------------------
    # Rust Tree-sitter Parser
    # -------------------------------------------------------------------------
    def _parse_rust(self, file_path: str, source_code: str) -> ParseResult:
        raw_loc = len(source_code.splitlines()) if source_code else 0
        if not source_code or not source_code.strip():
            return ParseResult(file_path=file_path, language="rust", is_success=True, raw_loc=raw_loc)

        try:
            tree = self._rust_parser.parse(source_code.encode("utf-8"))
        except Exception as exc:
            return ParseResult(file_path=file_path, language="rust", is_success=False, error_message=str(exc), raw_loc=raw_loc)

        root = tree.root_node
        entities: List[CodeEntity] = []
        imports: List[ImportEntity] = []
        call_sites: List[CallSite] = []
        error_nodes: List[ParseErrorNode] = []

        if root.has_error:
            self._collect_error_nodes(root, error_nodes)

        self._walk_rust(root, file_path, None, entities, imports, call_sites)

        return ParseResult(
            file_path=file_path,
            language="rust",
            is_success=True,
            has_syntax_errors=root.has_error,
            entities=entities,
            imports=imports,
            call_sites=call_sites,
            error_nodes=error_nodes,
            raw_loc=raw_loc,
        )

    def _walk_rust(self, node: Node, file_path: str, caller_id: Optional[str],
                   entities: List[CodeEntity], imports: List[ImportEntity], call_sites: List[CallSite]):
        ntype = node.type

        # Use declaration (imports)
        if ntype == "use_declaration":
            mod_text = node.text.decode("utf-8", errors="ignore").replace("use", "").replace(";", "").strip()
            imports.append(ImportEntity(module=mod_text, line_number=node.start_point.row + 1, is_from_import=True))
            return

        # Struct / Enum (Classes)
        if ntype in ("struct_item", "enum_item", "trait_item"):
            name_n = node.child_by_field_name("name")
            s_name = name_n.text.decode("utf-8", errors="ignore").strip() if name_n else "Item"
            ent_id = f"{file_path}::{s_name}"
            entities.append(CodeEntity(
                id=ent_id,
                name=s_name,
                entity_type=CodeEntityType.CLASS,
                file_path=file_path,
                start_line=node.start_point.row + 1,
                end_line=node.end_point.row + 1,
            ))

        # Function
        if ntype == "function_item":
            name_n = node.child_by_field_name("name")
            f_name = name_n.text.decode("utf-8", errors="ignore").strip() if name_n else "fn"
            ent_id = f"{file_path}::{f_name}"
            ent = CodeEntity(
                id=ent_id,
                name=f_name,
                entity_type=CodeEntityType.FUNCTION,
                file_path=file_path,
                start_line=node.start_point.row + 1,
                end_line=node.end_point.row + 1,
            )
            entities.append(ent)
            body = node.child_by_field_name("body")
            if body:
                for child in body.children:
                    self._walk_rust(child, file_path, ent.id, entities, imports, call_sites)
            return

        # Calls
        if ntype == "call_expression":
            fn_n = node.child_by_field_name("function")
            if fn_n:
                callee = fn_n.text.decode("utf-8", errors="ignore").strip()
                if "::" in callee:
                    callee = callee.split("::")[-1]
                call_sites.append(CallSite(caller_entity_id=caller_id, callee_name=callee, line_number=node.start_point.row + 1))

        for child in node.children:
            self._walk_rust(child, file_path, caller_id, entities, imports, call_sites)

    # -------------------------------------------------------------------------
    # C# Tree-sitter Parser
    # -------------------------------------------------------------------------
    def _parse_csharp(self, file_path: str, source_code: str) -> ParseResult:
        raw_loc = len(source_code.splitlines()) if source_code else 0
        if not source_code or not source_code.strip():
            return ParseResult(file_path=file_path, language="csharp", is_success=True, raw_loc=raw_loc)

        try:
            tree = self._csharp_parser.parse(source_code.encode("utf-8"))
        except Exception as exc:
            return ParseResult(file_path=file_path, language="csharp", is_success=False, error_message=str(exc), raw_loc=raw_loc)

        root = tree.root_node
        entities: List[CodeEntity] = []
        imports: List[ImportEntity] = []
        call_sites: List[CallSite] = []
        error_nodes: List[ParseErrorNode] = []

        if root.has_error:
            self._collect_error_nodes(root, error_nodes)

        self._walk_csharp(root, file_path, None, None, entities, imports, call_sites)

        return ParseResult(
            file_path=file_path,
            language="csharp",
            is_success=True,
            has_syntax_errors=root.has_error,
            entities=entities,
            imports=imports,
            call_sites=call_sites,
            error_nodes=error_nodes,
            raw_loc=raw_loc,
        )

    def _walk_csharp(self, node: Node, file_path: str, parent: Optional[CodeEntity], caller_id: Optional[str],
                     entities: List[CodeEntity], imports: List[ImportEntity], call_sites: List[CallSite]):
        ntype = node.type

        # Using directive (import)
        if ntype == "using_directive":
            line = node.start_point.row + 1
            mod_text = node.text.decode("utf-8", errors="ignore").replace("using", "").replace(";", "").strip()
            imports.append(ImportEntity(module=mod_text, line_number=line, is_from_import=True))
            return

        # Class / Struct / Interface
        if ntype in ("class_declaration", "struct_declaration", "interface_declaration"):
            name_n = node.child_by_field_name("name")
            c_name = name_n.text.decode("utf-8", errors="ignore").strip() if name_n else "Class"
            ent_id = f"{file_path}::{c_name}" if not parent else f"{parent.id}.{c_name}"
            ent = CodeEntity(
                id=ent_id,
                name=c_name,
                entity_type=CodeEntityType.CLASS,
                file_path=file_path,
                start_line=node.start_point.row + 1,
                end_line=node.end_point.row + 1,
                parent_id=parent.id if parent else None,
            )
            entities.append(ent)
            body = node.child_by_field_name("body")
            if body:
                for child in body.children:
                    self._walk_csharp(child, file_path, ent, caller_id, entities, imports, call_sites)
            return

        # Method / Constructor
        if ntype in ("method_declaration", "constructor_declaration"):
            name_n = node.child_by_field_name("name")
            m_name = name_n.text.decode("utf-8", errors="ignore").strip() if name_n else "Method"
            ent_id = f"{parent.id}.{m_name}" if parent else f"{file_path}::{m_name}"
            ent = CodeEntity(
                id=ent_id,
                name=m_name,
                entity_type=CodeEntityType.METHOD,
                file_path=file_path,
                start_line=node.start_point.row + 1,
                end_line=node.end_point.row + 1,
                parent_id=parent.id if parent else None,
            )
            entities.append(ent)
            body = node.child_by_field_name("body")
            if body:
                for child in body.children:
                    self._walk_csharp(child, file_path, ent, ent.id, entities, imports, call_sites)
            return

        # Calls
        if ntype == "invocation_expression":
            expr_n = node.child_by_field_name("expression")
            if expr_n:
                callee = expr_n.text.decode("utf-8", errors="ignore").strip()
                if "." in callee:
                    callee = callee.split(".")[-1]
                call_sites.append(CallSite(caller_entity_id=caller_id, callee_name=callee, line_number=node.start_point.row + 1))

        for child in node.children:
            self._walk_csharp(child, file_path, parent, caller_id, entities, imports, call_sites)

    # -------------------------------------------------------------------------
    # Universal Generic Heuristic Fallback (For Ruby, PHP, Kotlin, Swift, etc.)
    # -------------------------------------------------------------------------
    def _parse_generic_heuristic(self, file_path: str, source_code: str) -> ParseResult:
        raw_loc = len(source_code.splitlines()) if source_code else 0
        if not source_code or not source_code.strip():
            return ParseResult(file_path=file_path, language="generic", is_success=True, raw_loc=raw_loc)

        entities: List[CodeEntity] = []
        imports: List[ImportEntity] = []
        call_sites: List[CallSite] = []

        lines = source_code.splitlines()

        # Regex patterns for universal recognition
        class_regex = re.compile(r"^\s*(?:public|private|protected|export|abstract|final)*\s*class\s+([A-Za-z0-9_]+)", re.MULTILINE)
        fn_regex = re.compile(r"^\s*(?:public|private|protected|async|def|fn|fun|func|function|sub)\s+([A-Za-z0-9_]+)", re.MULTILINE)
        import_regex = re.compile(r"^\s*(?:import|require|include|using)\s+['\"]?([A-Za-z0-9_./\-]+)['\"]?", re.MULTILINE)
        call_regex = re.compile(r"\b([A-Za-z0-9_]+)\s*\(")

        current_entity: Optional[CodeEntity] = None

        for idx, line in enumerate(lines, 1):
            sline = line.strip()
            if not sline or sline.startswith(("//", "#", "/*", "*")):
                continue

            # Check imports
            imp_match = import_regex.search(line)
            if imp_match:
                imports.append(ImportEntity(module=imp_match.group(1), line_number=idx, is_from_import=True))
                continue

            # Check class
            cls_match = class_regex.search(line)
            if cls_match:
                c_name = cls_match.group(1)
                current_entity = CodeEntity(
                    id=f"{file_path}::{c_name}",
                    name=c_name,
                    entity_type=CodeEntityType.CLASS,
                    file_path=file_path,
                    start_line=idx,
                    end_line=min(idx + 30, len(lines)),
                )
                entities.append(current_entity)
                continue

            # Check function
            fn_match = fn_regex.search(line)
            if fn_match:
                f_name = fn_match.group(1)
                current_entity = CodeEntity(
                    id=f"{file_path}::{f_name}",
                    name=f_name,
                    entity_type=CodeEntityType.FUNCTION,
                    file_path=file_path,
                    start_line=idx,
                    end_line=min(idx + 20, len(lines)),
                )
                entities.append(current_entity)
                continue

            # Check calls
            for call_m in call_regex.finditer(line):
                callee = call_m.group(1)
                if callee not in ("if", "for", "while", "switch", "catch", "return", "function", "def", "class"):
                    call_sites.append(CallSite(
                        caller_entity_id=current_entity.id if current_entity else None,
                        callee_name=callee,
                        line_number=idx,
                    ))

        return ParseResult(
            file_path=file_path,
            language="generic",
            is_success=True,
            entities=entities,
            imports=imports,
            call_sites=call_sites,
            raw_loc=raw_loc,
        )

    def _collect_error_nodes(self, node: Node, error_nodes: List[ParseErrorNode]):
        """Collect syntax errors if any."""
        if getattr(node, "is_error", False) or node.type == "ERROR":
            error_nodes.append(ParseErrorNode(
                start_line=node.start_point.row + 1,
                end_line=node.end_point.row + 1,
                error_text=node.text.decode("utf-8", errors="ignore")[:100] if node.text else "(error)",
            ))
            return
        for child in node.children:
            if child.has_error:
                self._collect_error_nodes(child, error_nodes)

