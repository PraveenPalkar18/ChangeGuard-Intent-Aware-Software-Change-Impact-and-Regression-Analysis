# ChangeGuard: Data Pipeline Specification

## 1. Pipeline Overview
The ChangeGuard Data Pipeline coordinates the transformation of raw GitHub Pull Request inputs into structured, normalized code entities, diff hunks, and multi-language dependency graphs. This pipeline feeds the AI Intent Analysis layer, Change Graph Modeling, Impact Analysis, and Regression Test Recommendation engines.

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
│      Universal Multi-Language Code Parser              │
│  - Native Tree-sitter: Python, JS, TS, Go, Java,       │
│    Rust, C#                                            │
│  - Generic Regex Fallback: Ruby, PHP, Kotlin, Swift,   │
│    Dart, Scala, C/C++, Shell                           │
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
│  - AI Intent Analyzer (Groq / Gemini / TF-IDF)         │
│  - Change & Dependency Graph (NetworkX MultiDiGraph)   │
│  - Impact Propagation Engine (Reverse BFS Traversal)   │
│  - Multi-Language Regression Test Planner (P0-P3)      │
│  - Interactive SVG DAG Visual Graph & 3-Pillar UI      │
└────────────────────────────────────────────────────────┘
```

---

## 2. Pipeline Stages

### Stage 1: GitHub Ingestion (`backend/app/github/`)
- Interacts with GitHub REST API via read-only `GitHubClient`.
- Produces `PullRequestDetails`, containing metadata (`title`, `description`), commit entries (`PRCommit`), and changed file summaries (`PRFileChange`).
- Enforces rate-limit checks and token masking.

### Stage 2: Diff & Hunk Preprocessing (`backend/app/preprocessing/`)
- Standardizes raw unified diff text using `parse_patch()`.
- Extracts structured `DiffHunk` items with:
  - Header line (`@@ -old_start,old_lines +new_start,new_lines @@`)
  - Precise 1-indexed line numbers for all added lines (`added_line_numbers`) and deleted lines (`deleted_line_numbers`).
  - Distinguishes context lines from modified lines.

### Stage 3: Universal Code Parsing (`backend/app/repository/`)
- Accepts complete repository source files (not just snippets).
- Uses `UniversalCodeParser` to route files:
  - **Tree-sitter**: Python (`.py`), JavaScript (`.js`, `.jsx`), TypeScript (`.ts`, `.tsx`), Go (`.go`), Java (`.java`), Rust (`.rs`), and C# (`.cs`).
  - **Regex Fallback**: Ruby, PHP, Kotlin, Swift, Dart, Scala, C/C++, Shell, and other code extensions.
  - Extracts classes, structs, interfaces, methods, functions, calls, and imports.
  - Gracefully records syntax errors (`ParseErrorNode`) while preserving valid partial AST structures.

### Stage 4: Entity-Hunk Mapping (`EntityHunkMapper`)
- Connects hunk line ranges to AST entities:
  - **Enclosing Match**: The modified line range is fully contained within a function or method.
  - **Overlapping Match**: The change spans the boundary of an entity (e.g. signature or body modification).
  - **File-Level Match**: The change affects top-level code (e.g. global variables or module imports) outside any function/class.
  - **Old vs. New Source Line Disambiguation**: Deletions are mapped strictly against the old source AST to avoid falsely asserting that deleted functions exist in the new revision.

### Stage 5: Change Graph Modeling & Blast Radius (`backend/app/graph/` & `backend/app/impact/`)
- Builds an in-memory directed graph (`NetworkX MultiDiGraph`) representing code entities and call/import dependencies.
- Executes **Reverse Breadth-First Search (BFS)** starting from modified entities to trace downstream affected callers and importing modules.
- Distinguishes direct confirmed callers (`CONFIRMED_STATIC`, distance 1) from transitive callers (`POTENTIAL`, distance $\ge 2$).

### Stage 6: Multi-Language Test Selection (`backend/app/testing/`)
- Scans candidate test files matching naming patterns across ecosystems:
  - Python: `test_*.py`, `*_test.py`
  - JavaScript / TypeScript: `*.test.js`, `*.spec.ts`, `__tests__/`
  - Go: `*_test.go`
  - Java: `*Test.java`, `*Tests.java`
  - C#: `*Test.cs`, `*Tests.cs`
  - Rust: `tests/*.rs`
- Prioritizes tests into `P0_CRITICAL`, `P1_HIGH`, `P2_MEDIUM`, and `P3_LOW` tiers and formats ready-to-run CLI commands without executing arbitrary code.

---

## 3. Downstream Data Contracts

### Feed to AI Intent Analysis:
Each analyzed hunk is bundled with:
- PR title & stated description.
- Enclosing entity name, type, and docstring (e.g. `BillingService.processPayment`, method).
- Specific added and deleted code lines.

### Feed to Change Graph:
- Direct changed nodes: `CodeEntity.id` (e.g. `src/auth.ts::AuthManager.login`).
- Call edges: `CallSite` linkages (`caller_entity_id` $\rightarrow$ `callee_name`).
- Dependency edges: `ImportEntity` linkages (`file_path` $\rightarrow$ `module`).

### Feed to SVG DAG Visual Graph & Dashboard:
- 4 topological columns: `Changed Files` $\rightarrow$ `Modified Entities` $\rightarrow$ `Impacted Callers` $\rightarrow$ `Test Suites`.
- Directed bezier curved edges visualizing multi-hop impact with interactive node inspection.
- 3-Pillar summary cards (Explained, Unexplained, Uncertain hunks).
