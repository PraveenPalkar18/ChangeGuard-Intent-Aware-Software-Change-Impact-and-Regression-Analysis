# ChangeGuard: Architecture Specification

## 1. Architectural Philosophy
ChangeGuard is structured as a modular, monolithic application designed for maintainability, strict separation of concerns, high-speed execution, and thorough testability. It avoids unnecessary distributed complexity while enforcing strict interface boundaries between:
- API routing and configuration
- GitHub ingestion and rate limiting
- Multi-language AST parsing and diff mapping
- Modular AI intent analysis and model fallbacks
- Directed graph traversal and blast radius modeling
- Regression test selection and ranking
- Background monitoring and thread-safe persistence
- Native zero-dependency web dashboard

---

## 2. System Architecture Diagram

```
┌─────────────────────────────────────────────────────────────┐
│                       Client Layer                          │
│     (Native HTML5/CSS3/Vanilla JS Dashboard & CLI Runner)   │
│   - 3-Pillar Intent Cards (Explained, Unexplained, Uncertain)│
│   - Interactive SVG DAG Visual Dependency Graph (4 Columns) │
│   - Real-time Poller Controls & PR Detail Modal             │
└──────────────────────────────┬──────────────────────────────┘
                               │ HTTP / JSON
                               ▼
┌─────────────────────────────────────────────────────────────┐
│                      FastAPI Application                    │
│   ┌───────────────────────────────────────────────────────┐ │
│   │ /api/v1/github        /api/v1/analyze     /monitoring │ │
│   └──────────────────────────┬────────────────────────────┘ │
│                              │                              │
│   ┌──────────────────────────┴────────────────────────────┐ │
│   │                   Core & Configuration                │ │
│   │           (Pydantic Settings, Exceptions)             │ │
│   └───────────────────────────────────────────────────────┘ │
└──────────┬───────────────────┬───────────────────┬──────────┘
           │                   │                   │
           ▼                   ▼                   ▼
┌────────────────────┐ ┌────────────────┐ ┌────────────────────┐
│   GitHub Service   │ │ Code Parsing   │ │ Intent Analysis    │
│  - PyGithub Client │ │ - Diff Parser  │ │ - Groq Cloud LPU   │
│  - PR Importer     │ │ - UniversalAST │ │ - Google Gemini API│
│  - Polling Worker  │ │   (7 Langs)    │ │ - Local TF-IDF     │
│  - Rate Limiting   │ │ - RegexFallback│ │ - Mock Provider    │
└────────────────────┘ └────────────────┘ └────────────────────┘
           │                   │                   │
           └───────────────────┼───────────────────┘
                               ▼
┌─────────────────────────────────────────────────────────────┐
│              Change Graph & Impact Engine                   │
│   - NetworkX MultiDiGraph                                   │
│   - Entities (File, Class, Function, Test)                  │
│   - Reverse BFS Traversal & Blast Radius Calculation        │
│   - Multi-Language Regression Test Recommender (P0-P3)      │
└──────────────────────────────┬──────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────┐
│                  State & Persistence Layer                  │
│   - Atomic Persistent State Store (monitoring_state.json)   │
│   - Duplicate Suppression via PR Head Commit SHA Tracking   │
└─────────────────────────────────────────────────────────────┘
```

---

## 3. Directory Structure

```
ChangeGuard/
├── backend/
│   ├── app/
│   │   ├── api/
│   │   │   └── v1/
│   │   │       ├── router.py          # API v1 central router
│   │   │       ├── github.py          # GitHub endpoints (/pull-request, /rate-limit)
│   │   │       ├── analysis.py        # PR Analysis endpoints (/analyze/pull-request)
│   │   │       └── monitoring.py      # Background poller controls & repo management
│   │   ├── core/
│   │   │   ├── config.py              # Pydantic Settings & environment variables
│   │   │   └── exceptions.py          # Standardized domain exception hierarchy
│   │   ├── github/
│   │   │   ├── client.py              # PyGithub wrapper & error translation
│   │   │   ├── models.py              # PR metadata, file, and commit schemas
│   │   │   └── importer.py            # PR extraction logic
│   │   ├── preprocessing/             # Diff & hunk parser (DiffHunk, DiffLine, parse_patch)
│   │   ├── repository/                # AST code parsers
│   │   │   ├── parser_interface.py    # BaseCodeParser abstract interface
│   │   │   ├── tree_sitter_parser.py  # Python Tree-sitter parser
│   │   │   ├── universal_parser.py    # Universal Multi-Language Tree-sitter parser (JS/TS/Go/Java/Rust/C#)
│   │   │   ├── entity_mapper.py       # Entity-hunk association engine
│   │   │   └── models.py              # CodeEntity, ImportEntity, CallSite, ParseResult
│   │   ├── intent/                    # AI Intent Engine
│   │   │   ├── provider_interface.py  # AIModelProvider abstract base class
│   │   │   ├── analyzer_interface.py  # BaseIntentAnalyzer abstract base class
│   │   │   ├── factory.py             # Model provider factory with automatic fallback
│   │   │   ├── intent_analyzer.py     # Hunk intent classifier & explainability aggregator
│   │   │   ├── providers/
│   │   │   │   ├── groq_provider.py   # Groq Cloud LPU provider (Llama-3.3-70B, Qwen)
│   │   │   │   ├── gemini_provider.py # Google Gemini API provider (Gemini-2.5/3.8-Flash)
│   │   │   │   ├── tfidf_provider.py  # Local deterministic TF-IDF cosine baseline
│   │   │   │   └── mock_provider.py   # In-memory Jaccard token overlap for testing
│   │   │   └── models.py              # IntentResult, PRIntentReport, IntentClassification
│   │   ├── graph/                     # Change & Dependency Graph (NetworkX MultiDiGraph)
│   │   ├── impact/                    # Blast radius propagation & multi-factor risk engine
│   │   ├── testing/                   # Multi-language regression test selector (P0-P3)
│   │   ├── monitoring/                # Background PR poller & atomic state store
│   │   │   ├── poller.py              # Daemon thread polling configured repos
│   │   │   └── state_store.py         # Thread-safe atomic JSON persistence
│   │   ├── static/                    # Zero-dependency frontend
│   │   │   └── index.html             # Single-page dashboard with SVG DAG visualization
│   │   └── main.py                    # FastAPI application entrypoint & static mounting
│   ├── requirements.txt               # Pinned Python dependencies
│   └── tests/                         # 151 Automated unit and integration tests
│       ├── test_github_importer.py
│       ├── test_diff_parser.py
│       ├── test_tree_sitter_parser.py
│       ├── test_universal_parser.py   # Multi-language AST parser verification
│       ├── test_entity_mapper.py
│       ├── test_intent_analyzer.py
│       ├── test_groq_intent_provider.py
│       ├── test_gemini_intent_provider.py
│       ├── test_change_graph.py
│       ├── test_risk_analyzer.py
│       ├── test_test_selector.py
│       ├── test_monitoring.py
│       ├── test_evaluation.py
│       └── test_on_demand_workflow.py
├── docs/                              # Comprehensive project documentation
├── scripts/
│   ├── run_importer.py                # Standalone PR importer CLI
│   ├── run_evaluation.py              # Benchmark evaluation suite runner
│   ├── analyze_pr.py                  # On-demand terminal PR analyzer
│   ├── groq_smoke_test.py             # Groq API credential & latency test
│   └── gemini_smoke_test.py           # Gemini API credential & latency test
├── .env.example                       # Documented environment configuration template
├── pytest.ini                         # Pytest configuration
└── README.md                          # Quickstart developer guide
```

---

## 4. Key Design Decisions

### 4.1 Read-Only GitHub Integration
The system interacts with GitHub exclusively in read-only mode using official REST endpoints via `PyGithub`. It never pushes code, merges PRs, or modifies repository branches. Credentials are read strictly from environment variables (`GITHUB_TOKEN`) and never exposed in API outputs or logs.

### 4.2 Universal Multi-Language Parsing Architecture
Code parsing is handled by `UniversalCodeParser` in `backend/app/repository/universal_parser.py`:
- **Direct Tree-sitter Grammars**: Integrates pinned Tree-sitter packages for Python, JavaScript, TypeScript, Go, Java, Rust, and C#.
- **Generic Heuristic Fallback**: For languages without compiled native grammar packages installed (e.g. Ruby, PHP, Kotlin, Swift, Dart, Scala, C/C++, Shell), a robust regex-based heuristic extracts functions, classes, and method signatures so no code change is treated as an empty black box.
- **Syntax Error Isolation**: Files with syntax errors produce isolated `ParseErrorNode` records while still extracting all well-formed entities.

### 4.3 Pluggable AI Intent Engine with Resilient Fallback
The intent engine supports multiple high-performance cloud providers and a local deterministic baseline:
1. **Groq LPU Provider**: Delivers sub-second semantic evaluation using `llama-3.3-70b-versatile` or `qwen/qwen3.8-27b`.
2. **Google Gemini Provider**: Offers multi-modal reasoning with structured JSON schemas using `gemini-2.5-flash` or `gemini-3.8-flash`.
3. **Local TF-IDF Baseline**: 100% offline fallback computing cosine similarity across compound-token-expanded identifiers (`camelCase`, `snake_case`).
4. **Transparent Failover**: If an external provider experiences network disconnection, rate limiting, or authentication failure, `FallbackModelProvider` seamlessly routes the request to local TF-IDF, appending an explanatory warning without crashing.
5. **Secret Redaction**: Input text is scrubbed of GitHub tokens, Google API keys, and private keys prior to cloud transmission.

### 4.4 Change & Dependency Graph Traversal
The graph engine models repository relationships using a NetworkX `MultiDiGraph`:
- **Nodes**: Files, classes, functions, methods, and test suites.
- **Edges**: `CALLS`, `IMPORTS`, `CONTAINS`, `DEFINES`.
- **Blast Radius Calculation**: Traverses incoming edges using reverse BFS to identify all downstream callers and importing modules affected by modified entities.
- **Path Explainability**: Every impacted entity records its shortest path from the modified code hunk (e.g. `calc.py::add` $\rightarrow$ `service.py::calculate_total` $\rightarrow$ `controller.py::checkout`).

### 4.5 Multi-Language Regression Test Recommendation
The test selection engine maps modified and impacted entities to relevant test cases across diverse testing frameworks:
- Identifies Python (`pytest`, `unittest`), JavaScript/TypeScript (`jest`, `vitest`, `mocha`), Go (`go test`), Java (`junit`), C# (`nunit`, `xunit`), and Rust (`cargo test`).
- Prioritizes tests into:
  - `P0_CRITICAL`: Directly tests the modified entity.
  - `P1_HIGH`: Directly tests an immediate caller (distance 1) or imports the changed module.
  - `P2_MEDIUM`: Tests a transitive caller (distance $\ge 2$) or matches naming heuristics.
  - `P3_LOW`: Module-level fallback.
- Recommends actionable CLI commands (e.g., `pytest tests/test_auth.py -k test_refresh`) with zero automatic code execution.

### 4.6 Zero-Dependency Dashboard with SVG DAG Visualization
The dashboard (`backend/app/static/index.html`) is served directly by FastAPI without any frontend build pipeline:
- **3-Pillar Summary Cards**: Categorizes diff hunks into Explained, Unexplained, and Uncertain changes with clear explanations and collapsible code details.
- **Interactive SVG DAG Visual Graph**: Dynamically renders an interactive Directed Acyclic Graph across 4 topological columns (`Changed File` $\rightarrow$ `Modified Entity` $\rightarrow$ `Impacted Caller` $\rightarrow$ `Test Suite`).
- **Interactive Node Inspector**: Clicking any graph node highlights incoming/outgoing dependency edges and displays detailed metadata in a side inspector.
- **Focus on Core Metrics**: Decoupled from legacy composite risk badges on the frontend to present clean, actionable software engineering insights directly.

### 4.7 Automatic Background Polling & Atomic State Store
- Polling worker daemon (`PRPollingWorker`) automatically checks configured repositories at configurable intervals.
- `head_sha` tracking guarantees duplicate PR revisions are never re-analyzed redundantly.
- Thread-safe state store (`MonitoringStateStore`) uses atomic file operations (temp file write + OS rename) to persist state in `data/monitoring_state.json`.
