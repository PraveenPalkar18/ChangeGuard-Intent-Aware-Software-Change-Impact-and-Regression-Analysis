# ChangeGuard: Data Pipeline Specification

## 1. Pipeline Overview
The ChangeGuard Data Pipeline coordinates the transformation of raw GitHub Pull Request inputs into structured, normalized code entities and diff hunks. This pipeline serves as the primary data feed for AI Intent Analysis (M4) and Change Graph Modeling (M5).

```
┌────────────────────────────────────────────────────────┐
│                   GitHub Ingestion                     │
│  - PR Title & Markdown Description                     │
│  - Changed Files, Commit History & Unified Diff Patches│
└───────────────────────────┬────────────────────────────┘
                            │
                            ▼
┌────────────────────────────────────────────────────────┐
│             Preprocessing & Diff Parser                │
│  - Unified diff string tokenization                    │
│  - Line classification: Added (+), Deleted (-), Context│
│  - Line numbering: old_start/count, new_start/count    │
│  - Output: ParsedFileDiff & List[DiffHunk]             │
└─────────────┬────────────────────────────┬─────────────┘
              │                            │
              ▼                            ▼
┌───────────────────────────┐ ┌──────────────────────────┐
│   New Version Source      │ │   Old Version Source     │
│   (HEAD branch source)    │ │   (BASE branch source)   │
└─────────────┬─────────────┘ └────────────┬─────────────┘
              │                            │
              ▼                            ▼
┌────────────────────────────────────────────────────────┐
│           Tree-sitter Code Parser (Python)             │
│  - AST construction & syntax error tolerance           │
│  - Classes, standalone functions, class methods        │
│  - Imports (standard, aliased, from, relative)         │
│  - Call sites & enclosing caller identifiers           │
│  - Output: ParseResult (entities, calls, imports)      │
└─────────────┬────────────────────────────┬─────────────┘
              │                            │
              └─────────────┬──────────────┘
                            ▼
┌────────────────────────────────────────────────────────┐
│                  Entity-Hunk Mapper                    │
│  - Map added/modified lines to New AST entities        │
│  - Map deleted lines to Old AST entities               │
│  - Classify association: enclosing / overlapping /     │
│    file_level                                          │
│  - Output: List[EntityHunkAssociation]                 │
└───────────────────────────┬────────────────────────────┘
                            │
                            ▼
┌────────────────────────────────────────────────────────┐
│                 Downstream Consumers                   │
│  - M4: Intent Analyzer (Hunk vs PR Description)        │
│  - M5: Change Graph (NetworkX Nodes & Edges)           │
│  - M6: Impact Propagation Engine                       │
│  - M7: Targeted Regression Test Planner                │
└────────────────────────────────────────────────────────┘
```

---

## 2. Pipeline Stages

### Stage 1: GitHub Ingestion (`backend/app/github/`)
- Interacts with GitHub REST API via read-only `GitHubClient`.
- Produces `PullRequestDetails`, containing metadata (`title`, `description`), commit entries (`PRCommit`), and changed file summaries (`PRFileChange`).

### Stage 2: Diff & Hunk Preprocessing (`backend/app/preprocessing/`)
- Standardizes raw unified diff text using `parse_patch()`.
- Extracts structured `DiffHunk` items with:
  - Header line (`@@ -old_start,old_lines +new_start,new_lines @@`)
  - Precise 1-indexed line numbers for all added lines (`added_line_numbers`) and deleted lines (`deleted_line_numbers`).
  - Distinguishes context lines from modified lines.

### Stage 3: Source Code Parsing (`backend/app/repository/`)
- Accepts complete repository source files (not just partial snippets).
- Uses `TreeSitterPythonParser` to extract:
  - Entities with 1-indexed start and end line ranges (`CodeEntity`).
  - Module import statements (`ImportEntity`).
  - Function and method call expressions with caller tracing (`CallSite`).
  - Gracefully records syntax errors (`ParseErrorNode`) while recovering partial entities.

### Stage 4: Entity-Hunk Mapping (`EntityHunkMapper`)
- Connects hunk line ranges to AST entities:
  - **Enclosing Match**: The modified line range is fully contained within a function or method.
  - **Overlapping Match**: The change spans the boundary of an entity (e.g. signature or body modification).
  - **File-Level Match**: The change affects top-level code (e.g. global variables or module imports) outside any function/class.
  - **Old vs. New Source Line Disambiguation**: Deletions are mapped strictly against the old source AST to avoid falsely asserting that deleted functions exist in the new revision.

---

## 3. Downstream Data Contracts

### Feed to M4 (AI Intent Analysis):
Each analyzed hunk is bundled with:
- PR title & stated description.
- Enclosing entity name, type, and docstring (e.g. `Calculator.add`, method).
- Specific added and deleted code lines.

### Feed to M5 (Change Graph):
- Direct changed nodes: `CodeEntity.id` (e.g. `calc.py::Calculator.add`).
- Call edges: `CallSite` linkages (`caller_entity_id` -> `callee_name`).
- Dependency edges: `ImportEntity` linkages (`file_path` -> `module`).
