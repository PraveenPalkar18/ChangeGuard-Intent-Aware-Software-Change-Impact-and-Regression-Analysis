# ChangeGuard: Architecture Specification

## 1. Architectural Philosophy
ChangeGuard is structured as a modular, monolithic application designed for maintainability, strict separation of concerns, and ease of testing. It avoids unnecessary distributed complexity (such as microservices) while enforcing strict interface boundaries between the API, GitHub data layer, code parsers, AI providers, graph engines, and persistence.

---

## 2. System Architecture Diagram

```
┌─────────────────────────────────────────────────────────────┐
│                       Client Layer                          │
│               (React + Tailwind Dashboard / CLI)            │
└──────────────────────────────┬──────────────────────────────┘
                               │ HTTP / JSON
                               ▼
┌─────────────────────────────────────────────────────────────┐
│                      FastAPI Application                    │
│   ┌───────────────────────────────────────────────────────┐ │
│   │ /api/v1/github        /api/v1/analyze     /api/v1/... │ │
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
│  - PyGithub Client │ │ - Diff Parser  │ │ - AIProvider       │
│  - PR Importer     │ │ - Tree-sitter  │ │ - Model Abstraction│
│  - Rate Limiting   │ │ - AST Walker   │ │ - Embedding/LLM    │
└────────────────────┘ └────────────────┘ └────────────────────┘
           │                   │                   │
           └───────────────────┼───────────────────┘
                               ▼
┌─────────────────────────────────────────────────────────────┐
│              Change Graph & Impact Engine                   │
│   - NetworkX Directed Graph                                 │
│   - Entities (File, Class, Function, Test)                  │
│   - Impact Propagation & Regression Test Planner            │
└──────────────────────────────┬──────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────┐
│              Persistence Layer (PostgreSQL)                 │
│   (Users, Repositories, PRs, Analyses, Reports)             │
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
│   │   │       ├── router.py       # API v1 central router
│   │   │       ├── github.py       # GitHub endpoints (/pull-request, /rate-limit)
│   │   │       └── analysis.py     # PR Analysis endpoint (/analyze/pull-request)
│   │   ├── core/
│   │   │   ├── config.py           # Pydantic Settings & environment variables
│   │   │   └── exceptions.py       # Standardized domain exception hierarchy
│   │   ├── github/
│   │   │   ├── client.py           # PyGithub wrapper & error translation
│   │   │   ├── models.py           # PR metadata, file, and commit schemas
│   │   │   └── importer.py         # PR extraction logic
│   │   ├── preprocessing/          # Diff & hunk parser (DiffHunk, DiffLine, parse_patch)
│   │   ├── repository/             # AST / Tree-sitter parsers (TreeSitterPythonParser, EntityHunkMapper)
│   │   ├── intent/                 # AI Intent Engine (AIModelProvider, IntentAnalyzer, TF-IDF, CodeBERT)
│   │   ├── analysis/               # Orchestration pipeline (ChangeGuardAnalysisService, models)
│   │   ├── graph/                  # Change & Dependency Graph (ChangeGraphBuilder, models, impact traversal)
│   │   ├── impact/                 # Impact analysis & Risk Ranking (RiskAnalyzer, models, multi-factor scoring)
│   │   ├── testing/                # Regression test recommender (RegressionTestSelector, models, ranking)
│   │   ├── database/               # [Milestone 8] SQLAlchemy / PostgreSQL models
│   │   ├── auth/                   # [Milestone 8] JWT & user security
│   │   └── main.py                 # FastAPI application entrypoint
│   ├── requirements.txt            # Python dependencies
│   └── tests/
│       ├── conftest.py             # Fixtures and mocks
│       ├── test_github_importer.py # Unit, integration, and API tests
│       ├── test_diff_parser.py     # Diff hunk extraction and line mapping tests
│       ├── test_tree_sitter_parser.py # Tree-sitter AST parsing tests
│       ├── test_entity_mapper.py   # Entity-hunk association tests
│       ├── test_intent_analyzer.py # AI Intent engine and fallback tests
│       ├── test_analysis_service.py # End-to-end integration pipeline tests
│       ├── test_change_graph.py    # Change & dependency graph and traversal tests
│       ├── test_risk_analyzer.py   # Risk ranking, blast radius, and cycle safety tests
│       ├── test_test_selector.py   # Regression test selection, ranking, and heuristics tests
│       ├── test_monitoring.py      # Background poller, state store, and dashboard tests
│       └── test_evaluation.py      # Benchmark evaluation framework tests
├── docs/                           # Living project documentation
├── scripts/
│   ├── run_importer.py             # CLI runner for quick PR inspection
│   └── run_evaluation.py          # Benchmark evaluation suite CLI runner
├── .env.example                    # Sample environment variables
├── .gitignore                      # Git ignore definitions
├── pytest.ini                      # Pytest configuration
└── README.md                       # Developer setup and guide
```

---

## 4. Key Design Decisions

### 4.1 Read-Only GitHub Integration
The system interacts with GitHub exclusively in read-only mode using official REST endpoints via `PyGithub`. It never pushes code, merges PRs, or modifies repository branches. Credentials are read strictly from environment variables (`GITHUB_TOKEN`) and never exposed in API outputs or logs.

### 4.2 Standardized Exception Translation
Raw PyGithub exceptions (`BadCredentialsException`, `UnknownObjectException`, `RateLimitExceededException`) are intercepted and translated into typed ChangeGuard domain exceptions (`GitHubAuthenticationException`, `GitHubResourceNotFoundException`, `GitHubRateLimitExceededException`). This guarantees:
- Predictable HTTP status codes (401, 404, 429, 502).
- Clean JSON error payloads without leaking stack traces or credentials.

### 4.3 Pluggable Component Boundaries
Each component (Tree-sitter parser, AI Intent Analyzer, Graph Engine, Risk Analyzer, Test Selector, Monitoring Worker) interacts exclusively via typed Pydantic models and explicit constructor injection.

### 4.4 Multi-Factor Risk Ranking Engine (Milestone 6)
Risk ranking assigns an explainable tier (`LOW`, `MEDIUM`, `HIGH`) and composite normalized score based on documented structural and semantic evidence:
1. **Downstream Blast Radius**: Downstream entity caller count, external dependent files count, and BFS propagation depth.
2. **Change Scope & Volatility**: Total additions/deletions, hunk frequency, and modified file count.
3. **Intent Alignment**: Correlation with stated PR intent; unexplained changes affecting callers elevate risk. Note: A low semantic similarity score alone never triggers HIGH risk on isolated leaf code.
4. **Dependency Resolvability & Blind Spots**: Unresolved internal imports, syntax errors, or unparsed files are tracked in limitations and categorized as `UNKNOWN` relationships rather than invented edges.
5. **Relationship Verification**: Confirmed direct static relationships (`CONFIRMED_STATIC`, distance 1) are distinguished from indirect transitive paths (`POTENTIAL`, distance >= 2) and unresolved blind spots (`UNKNOWN`). Every HIGH result is backed by concrete `high_risk_reasons` and explainable `primary_impact_paths`.

### 4.5 Targeted Regression Test Selection Engine (Milestone 7)
Regression test selection identifies and prioritizes the exact test cases needed to verify Pull Request changes:
1. **Discovery**: Identifies Python test files (`test_*.py`, `*_test.py`, `tests/`) and test entities (functions, methods, `TestCase` classes).
2. **Multi-Source Mapping**:
   - `STATIC_CALL`: Test body directly calls modified or impacted code in AST.
   - `STATIC_IMPORT`: Test module statically imports the modified file or entity.
   - `TRANSITIVE_GRAPH`: Test exercises a downstream dependent reached through multi-hop dependency graph.
   - `NAMING_HEURISTIC`: Transparent symbol or file name correlation (e.g. `test_billing.py` -> `billing.py`, `test_discount` -> `discount`).
3. **Prioritization Tiers**:
   - `P0_CRITICAL`: Direct verification of changed code.
   - `P1_HIGH`: Verification of direct downstream callers (distance 1) or module import.
   - `P2_MEDIUM`: Transitive callers (distance >= 2) or naming heuristic matches.
   - `P3_LOW`: General module-level correlation.
4. **Safety & Zero Auto-Execution**: ChangeGuard never executes arbitrary PR code automatically. Test selection is deterministic static recommendation accompanied by suggested test runner commands (e.g. `pytest tests/test_billing.py -k test_discount`). No test passing or failing claims are made without verified execution.

### 4.6 Automatic PR Monitoring and Duplicate Suppression (Milestone 8)
1. **Local Background Polling**: A lightweight background daemon thread (`PRPollingWorker`) polls configured GitHub repositories at user-defined intervals (default 60s). Polling requires zero public webhooks or paid cloud infrastructure.
2. **Duplicate Suppression**: Tracks the last analyzed `head_sha` for every PR revision. If the PR commit hash has not changed, processing is skipped with zero redundant re-analysis. When a new commit is pushed, re-analysis triggers automatically.
3. **Atomic State Persistence**: Repository configurations and PR state records are persisted in a thread-safe atomic JSON file (`data/monitoring_state.json`), enabling instant recovery upon application restart without re-analyzing past PRs.
4. **Resilient Lifecycle & Rate Limiting**: Tracks status transitions (`pending` -> `running` -> `completed` / `failed`). Checks remaining GitHub API quota before polling cycles, backing off cleanly when rate limits approach exhaustion. Retries failed analyses up to `MAX_PROCESSING_RETRIES` (default 3) without infinite loops.

### 4.7 Zero-Dependency Local Dashboard & Safe Reporting (Milestone 9)
1. **Direct FastAPI Serving**: The dashboard UI (`backend/app/static/index.html`) is served directly by the backend server at `/` and `/dashboard` using native HTML, CSS glassmorphism, and Vanilla JS. It requires zero Node.js/npm dependencies, zero build steps, and zero bundlers.
2. **Comprehensive PR Inspection**: Visualizes real-time poller status, monitored repositories, intent classification findings with evidence, dependency impact paths, risk breakdown, and ranked regression tests.
3. **Safe Read-Only Reporting Default**: GitHub issue commenting is strictly disabled by default (`ENABLE_GITHUB_REPORTING=false`). Write permissions must be explicitly enabled by configuration, safeguarding remote repositories against unauthorized comments.

### 4.8 Repeatable Empirical Benchmark Evaluation (Milestone 10)
1. **Curated Fixture Suite**: 4 realistic architectural pull request scenarios with ground-truth labels for intent (`EXPLAINED`, `UNEXPLAINED`, `UNCERTAIN`), graph impact entities, and regression tests.
2. **Transparent Metrics Reporting**: Calculates precision, recall, F1, confusion matrices, and test hit-rate coverage without inventing scores or claiming unverified production accuracy. Explicitly identifies false positives, false negatives, and architectural boundaries.
