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
│   │   ├── graph/                  # [Milestone 5] NetworkX change graph
│   │   ├── impact/                 # [Milestone 6] Impact analysis & propagation
│   │   ├── testing/                # [Milestone 7] Regression test recommender
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
│       └── test_analysis_service.py # End-to-end integration pipeline tests
├── docs/                           # Living project documentation
├── scripts/
│   └── run_importer.py             # CLI runner for quick PR inspection
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
Each upcoming component (Tree-sitter parser, AI Intent Analyzer, Graph Engine) interacts exclusively via typed Pydantic models and abstract base classes.
