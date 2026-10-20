# ChangeGuard Development Log

---

### Entry: 2026-10-08 - Milestone 1: Backend Foundation & GitHub PR Importer

- **Date**: 2026-10-08
- **Task**: Milestone 1 - Initial backend structure, environment setup, GitHub API authentication, and read-only PR Importer.
- **What was implemented**:
  1. Initialized repository with Git (`main` branch) and Python 3.12 virtual environment (`.venv`).
  2. Created core backend configuration module using `pydantic-settings` to safely read environment variables (`GITHUB_TOKEN`, app settings) from `.env`.
  3. Created a typed domain exception hierarchy (`ChangeGuardException`, `GitHubAuthenticationException`, `GitHubResourceNotFoundException`, `GitHubRateLimitExceededException`, `GitHubAPIException`).
  4. Implemented `GitHubClient` wrapping PyGithub with error translation and read-only semantics.
  5. Implemented `GitHubPRImporter` service extracting PR title, body description, author, branch refs, commit history, changed files, line modification counts, and diff patch hunks.
  6. Implemented FastAPI router with endpoints (`/api/v1/github/pull-request/import`, `/api/v1/github/pull-request/{owner}/{repo}/{pr_number}`, and `/api/v1/github/rate-limit`).
  7. Built standalone CLI tool (`scripts/run_importer.py`) allowing instant terminal inspection of any public or authenticated GitHub PR.
  8. Configured `pytest` with test suite covering unit, exception, and API integration paths with mocked GitHub objects.
  9. Tested live against real GitHub repositories (`octocat/Hello-World` PR #1, `pallets/flask` PR #5000).

- **Files changed**:
  - `.gitignore` (Created)
  - `.env.example` (Created)
  - `requirements.txt` (Created)
  - `backend/requirements.txt` (Created)
  - `pytest.ini` (Created)
  - `backend/__init__.py` (Created)
  - `backend/app/__init__.py` (Created)
  - `backend/app/core/__init__.py` (Created)
  - `backend/app/core/config.py` (Created)
  - `backend/app/core/exceptions.py` (Created)
  - `backend/app/github/__init__.py` (Created)
  - `backend/app/github/models.py` (Created)
  - `backend/app/github/client.py` (Created)
  - `backend/app/github/importer.py` (Created)
  - `backend/app/api/__init__.py` (Created)
  - `backend/app/api/v1/__init__.py` (Created)
  - `backend/app/api/v1/router.py` (Created)
  - `backend/app/api/v1/github.py` (Created)
  - `backend/app/main.py` (Created)
  - `backend/tests/__init__.py` (Created)
  - `backend/tests/conftest.py` (Created)
  - `backend/tests/test_github_importer.py` (Created)
  - `scripts/run_importer.py` (Created)
  - `docs/PROJECT_OVERVIEW.md` (Created)
  - `docs/ARCHITECTURE.md` (Created)
  - `docs/API.md` (Created)
  - `docs/DEVELOPMENT_LOG.md` (Created)

- **Dependencies added**:
  - `fastapi` & `uvicorn[standard]`: Modern asynchronous ASGI web framework for REST API endpoints.
  - `pydantic` & `pydantic-settings`: Schema definition, validation, and type-safe environment configuration.
  - `python-dotenv`: Local `.env` file loading.
  - `PyGithub`: Official Python SDK for interacting with GitHub REST API v3.
  - `pytest`, `pytest-asyncio`, `httpx`: Testing framework and HTTP client for FastAPI TestClient.

- **Tests added**:
  - `test_importer_success`: Verifies complete data mapping from PyGithub objects to Pydantic models.
  - `test_importer_handles_null_optional_fields`: Verifies robustness against missing PR descriptions, null commit dates, and empty diffs.
  - `test_client_bad_credentials_exception`: Verifies HTTP 401 mapping when token is invalid.
  - `test_client_unknown_object_exception`: Verifies HTTP 404 mapping when repo/PR does not exist.
  - `test_client_rate_limit_exception`: Verifies HTTP 429 mapping on quota exhaustion.
  - `test_client_generic_github_exception`: Verifies HTTP 500/502 mapping on general upstream failures.
  - `test_health_check`: Validates `/health` and `/api/v1/health` responses.
  - `test_api_import_pr_payload_success`: Validates `POST /api/v1/github/pull-request/import`.
  - `test_api_import_pr_path_param_success`: Validates `GET /api/v1/github/pull-request/{owner}/{repo}/{pr_number}`.
  - `test_api_import_pr_not_found`: Validates 404 error envelope.
  - `test_api_import_pr_rate_limited`: Validates 429 error envelope.
  - `test_api_invalid_request_payload`: Validates 422 Pydantic validation failure.

- **Problems encountered**:
  1. *PyGithub 2.x rate limit attribute change*: `g.get_rate_limit().core` raised `AttributeError` because PyGithub 2.x uses `rate_limit_obj.rate`.
     - *Solution*: Added fallback check for `getattr(rate_limit_obj, "rate", None) or getattr(rate_limit_obj, "core", None)`.
  2. *Windows Console Charset encoding*: Unicode checkmarks (`✓`) and bullet points (`•`) caused `charmap codec can't encode character` when running the CLI runner in Windows command shells with legacy code pages.
     - *Solution*: Replaced unicode symbols with ASCII equivalents (`[SUCCESS]` and `*`) ensuring cross-platform stability.
  3. *Module import resolution in tests*: Running pytest initially failed with `ModuleNotFoundError: No module named 'backend'`.
     - *Solution*: Created `pytest.ini` with `pythonpath = .` and added `backend/__init__.py`.

- **Current status**:
  Milestone 1 complete. GitHub Personal Access Token configured in git-ignored `.env` file and verified (API rate limit verified at 5,000 requests/hour). 12/12 automated tests passing cleanly.

- **Next step**:
  Milestone 2 & 3: Unified diff parsing and Tree-sitter Code Parsing.

---

### Entry: 2026-10-12 - Milestone 3: Tree-sitter Code Parsing & Diff Integration

- **Date**: 2026-10-12
- **Task**: Milestone 3 - Tree-sitter Python code parsing, entity extraction, unified diff hunk processing, and entity-hunk association.
- **What was implemented**:
  1. Built diff preprocessing package (`backend/app/preprocessing/`):
     - `models.py`: `DiffLineType`, `DiffLine`, `DiffHunk`, and `ParsedFileDiff` representing hunks, line mappings, and added/deleted lines.
     - `diff_parser.py`: Robust parser converting raw unified diff patches into structured hunks with 1-indexed old/new line numbers.
  2. Built repository code parsing package (`backend/app/repository/`):
     - `parser_interface.py`: `BaseCodeParser` abstract interface for extensible language parsers.
     - `models.py`: Typed models for `CodeEntity` (classes, functions, methods, async, decorators, docstrings, parameters), `ImportEntity` (standard, aliased, from, relative), `CallSite` (invocations and caller tracing), `ParseErrorNode`, `ParseResult`, and `EntityHunkAssociation`.
     - `tree_sitter_parser.py`: High-performance Python AST parser using `tree-sitter` and `tree-sitter-python`. Extracts classes, standalone functions, methods, nested functions, decorators, async markers, docstrings, parameters, imports, and calls. Detects and isolates syntax error nodes while preserving valid partial AST structures. Explicitly rejects unsupported languages.
     - `entity_mapper.py`: `EntityHunkMapper` associating diff hunks to code entities with old vs new line number awareness. Maps added/modified lines to new AST and deleted lines to old AST without falsely claiming deleted entities exist in new source.
  3. Created documentation:
     - `docs/CODE_PARSING.md`: Comprehensive specification of grammar, entity schema, call extraction, concrete examples, and limitations.
     - `docs/DATA_PIPELINE.md`: End-to-end data flow from PR ingestion through diff parsing, AST analysis, and downstream contracts.
     - Updated `docs/ARCHITECTURE.md`.
  4. Expanded automated test suite with 16 new unit tests (28 tests total across the project):
     - `test_diff_parser.py`: Single and multi-hunk parsing, line tracking, empty patches, integration with `PRFileChange`.
     - `test_tree_sitter_parser.py`: Standalone functions, classes, methods, nested functions, decorators, async, imports, calls, empty/comment files, syntax errors with partial recovery, unsupported language rejection.
     - `test_entity_mapper.py`: Method modification (enclosing), new function addition, deletion with old vs new source distinction, file-level changes.

- **Files changed**:
  - `backend/requirements.txt` (Added `tree-sitter>=0.22.0` and `tree-sitter-python>=0.21.0`)
  - `backend/app/preprocessing/__init__.py` (Created)
  - `backend/app/preprocessing/models.py` (Created)
  - `backend/app/preprocessing/diff_parser.py` (Created)
  - `backend/app/repository/__init__.py` (Created)
  - `backend/app/repository/models.py` (Created)
  - `backend/app/repository/parser_interface.py` (Created)
  - `backend/app/repository/tree_sitter_parser.py` (Created)
  - `backend/app/repository/entity_mapper.py` (Created)
  - `backend/tests/test_diff_parser.py` (Created)
  - `backend/tests/test_tree_sitter_parser.py` (Created)
  - `backend/tests/test_entity_mapper.py` (Created)
  - `docs/CODE_PARSING.md` (Created)
  - `docs/DATA_PIPELINE.md` (Created)
  - `docs/ARCHITECTURE.md` (Updated)
  - `docs/DEVELOPMENT_LOG.md` (Updated)

- **Dependencies added**:
  - `tree-sitter>=0.22.0`: Core Tree-sitter runtime bindings.
  - `tree-sitter-python>=0.21.0`: Official Tree-sitter Python grammar.

- **Tests added**:
  - `test_parse_patch_basic`: Verifies unified diff hunk extraction and line arithmetic.
  - `test_parse_patch_multiple_hunks`: Verifies multi-hunk patch separation.
  - `test_parse_patch_empty_or_none`: Edge-case testing for empty/None patches.
  - `test_parse_file_diff_integration`: Verifies integration between PRFileChange and ParsedFileDiff.
  - `test_parse_simple_function_and_class`: Validates class, method, function, parameters, and docstrings.
  - `test_parse_nested_functions`: Validates inner function parent_id and namespacing.
  - `test_parse_decorators_and_async`: Validates `@decorator` and `async def` extraction.
  - `test_parse_imports`: Validates standard, aliased, and from-imports.
  - `test_parse_call_sites`: Validates call site extraction and caller tracking.
  - `test_empty_and_comment_files`: Validates edge cases for non-code files.
  - `test_syntax_errors_and_partial_recovery`: Validates partial recovery on malformed source.
  - `test_unsupported_language_rejection`: Validates rejection of non-Python files.
  - `test_map_hunk_enclosed_in_method`: Validates method-enclosed modification association.
  - `test_map_hunk_new_function_addition`: Validates newly added function association.
  - `test_map_hunk_deletion_old_source_distinction`: Validates old vs new AST deletion separation.
  - `test_map_hunk_file_level_change`: Validates module-level non-entity changes.

- **Problems encountered**:
  1. *BaseCodeParser circular/missing import in tree_sitter_parser*: `tree_sitter_parser.py` initially imported `BaseCodeParser` from `models` instead of `parser_interface`.
     - *Solution*: Corrected import source to `parser_interface`.
  2. *Diff line number test arithmetic expectation*: Initial unit test expected line numbers `[12, 13]` for additions, but 1-indexed count after context line 10 evaluated to `[11, 12]`.
     - *Solution*: Verified unified diff mathematical specification and corrected test assertions.

- **Current status**:
  Milestone 3 complete. All 28 automated tests passing (12 M1 tests + 16 M2/M3 tests). Clean separation maintained between GitHub API, Tree-sitter parsing, and future AI models.

- **Next step**:
  Milestone 4: Modular AI Intent Analysis Engine.

---

### Entry: 2026-10-12 - Milestone 4: Modular AI Intent Engine & Pluggable Providers

- **Date**: 2026-10-12
- **Task**: Milestone 4 - Modular AI Intent Engine, model provider abstractions, TF-IDF baseline, CodeBERT integration, and hunk classification.
- **What was implemented**:
  1. Built modular AI interfaces (`backend/app/intent/`):
     - `provider_interface.py`: Abstract `AIModelProvider` with `compute_similarity()` and `get_model_info()`.
     - `analyzer_interface.py`: Abstract `BaseIntentAnalyzer` defining `analyze_hunk()` and `analyze_pull_request()`.
     - `models.py`: Pydantic data schemas: `PRContext`, `HunkContext`, `HunkIntentResult`, `PRIntentReport`, and `IntentClassification` enum (`EXPLAINED`, `UNEXPLAINED`, `UNCERTAIN`).
  2. Implemented AI model providers (`backend/app/intent/providers/`):
     - `MockAIProvider`: Deterministic word-level Jaccard overlap provider for offline test environments.
     - `TFIDFSimilarityProvider`: Unigram TF-IDF cosine similarity provider with compound identifier sub-token expansion (camelCase and snake_case) and zero-dependency native fallback.
     - `CodeBERTSimilarityProvider`: Contextual transformer embedding provider using `microsoft/codebert-base` with mean pooling, 512-token truncation, and explicit dependency checks (`ModelNotAvailableException`).
  3. Built model factory & fallback orchestration (`backend/app/intent/factory.py`):
     - `create_model_provider()`: Reads configuration from environment (`AI_PROVIDER`, `AI_MODEL`) without hardcoding model names in business logic.
     - `FallbackModelProvider`: Transparently catches primary provider failures (e.g. GPU out-of-memory or missing weights) and reroutes inference to a secondary provider (e.g. `tfidf`), logging warnings and never fabricating fake results.
  4. Implemented `IntentAnalyzer` (`backend/app/intent/intent_analyzer.py`):
     - Classifies hunks into `EXPLAINED`, `UNEXPLAINED`, or `UNCERTAIN`.
     - Heuristic safeguards: direct entity mention matching, test suite supporting artifact heuristics, and explicit `UNCERTAIN` classification when PR descriptions are absent or when semantic alignment is partial/ambiguous.
     - Produces explainable reasons, supporting evidence list, and explicit decision limitations.
     - Aggregates full-PR statistics into `PRIntentReport`.
  5. Created comprehensive documentation:
     - `docs/AI_MODELS.md`: Specifications for baseline and transformer models, input/output contracts, thresholds, and limitations.
     - `docs/MODEL_SWITCHING.md`: Step-by-step developer instructions for swapping models or plugging new providers.
     - Updated `docs/ARCHITECTURE.md`.
  6. Added 13 new unit tests in `backend/tests/test_intent_analyzer.py` (41 tests passing total across the project).

- **Files changed**:
  - `backend/requirements.txt` (Added `scikit-learn>=1.4.0` and `numpy>=1.26.0`)
  - `backend/app/intent/__init__.py` (Created)
  - `backend/app/intent/models.py` (Created)
  - `backend/app/intent/provider_interface.py` (Created)
  - `backend/app/intent/analyzer_interface.py` (Created)
  - `backend/app/intent/providers/__init__.py` (Created)
  - `backend/app/intent/providers/mock_provider.py` (Created)
  - `backend/app/intent/providers/tfidf_provider.py` (Created)
  - `backend/app/intent/providers/codebert_provider.py` (Created)
  - `backend/app/intent/factory.py` (Created)
  - `backend/app/intent/intent_analyzer.py` (Created)
  - `backend/tests/test_intent_analyzer.py` (Created)
  - `docs/AI_MODELS.md` (Created)
  - `docs/MODEL_SWITCHING.md` (Created)
  - `docs/ARCHITECTURE.md` (Updated)
  - `docs/DEVELOPMENT_LOG.md` (Updated)

- **Dependencies added**:
  - `scikit-learn>=1.4.0`: TF-IDF vectorization and cosine similarity.
  - `numpy>=1.26.0`: Numerical array manipulation.

- **Tests added**:
  - `test_mock_provider_deterministic`: Deterministic Jaccard overlap check.
  - `test_tfidf_provider_similarity`: TF-IDF cosine similarity on related vs orthogonal text.
  - `test_tfidf_provider_empty_inputs`: Graceful zero handling for empty text.
  - `test_codebert_provider_fallback_when_unavailable`: Diagnostic metadata check and dependency validation.
  - `test_fallback_wrapper_switching`: Dynamic provider switching upon primary failure.
  - `test_factory_creation`: Configuration-driven provider instantiation.
  - `test_analyze_hunk_explained_by_high_similarity`: EXPLAINED classification on semantic alignment.
  - `test_analyze_hunk_explained_by_direct_entity_mention`: EXPLAINED classification on direct symbol reference.
  - `test_analyze_hunk_unexplained_orthogonal_change`: UNEXPLAINED classification on unrelated change.
  - `test_analyze_hunk_uncertain_on_empty_intent`: UNCERTAIN classification when PR description is missing.
  - `test_analyze_hunk_uncertain_on_ambiguous_partial_overlap`: UNCERTAIN classification on intermediate overlap.
  - `test_analyze_hunk_test_file_heuristic`: Supporting test suite heuristic validation.
  - `test_analyze_pull_request_aggregate_report`: Aggregation and summary generation across PR hunks.

- **Problems encountered**:
  1. *Bigram dilution in short code/intent pairs*: TF-IDF with `ngram_range=(1, 2)` produced low similarity scores (~0.07) on short snippet pairs due to excessive non-overlapping bigrams.
     - *Solution*: Switched to unigram TF-IDF and implemented code identifier sub-token expansion (splitting camelCase and snake_case into sub-words like `calculate` + `discount`).
  2. *Threshold calibration for natural language vs code*: Raw text similarity between informal English descriptions and Python code rarely exceeds 0.50 even on identical features.
     - *Solution*: Calibrated thresholds (`explained_threshold=0.20`, `unexplained_threshold=0.05`), complemented by direct symbol mention heuristics.

- **Current status**:
  Milestone 4 complete. 41/41 automated tests passing across the codebase. Zero hard-coded model identifiers or API keys in business logic.

- **Next step**:
  End-to-End Integration Audit & Analysis Service implementation before proceeding to Milestone 5.

---

### Entry: 2026-10-19 - End-to-End Integration Audit & Analysis Pipeline Service

- **Date**: 2026-10-19
- **Task**: Audit integration between M1 (GitHub Importer), M2 (Diff Preprocessor), M3 (Tree-sitter Code Parser), and M4 (AI Intent Engine). Implement orchestrating analysis service and public API endpoint without treating patches as full source.
- **Audit Findings**:
  1. *Missing Orchestration Service*: M1, M2, M3, and M4 functioned in isolation with high test coverage, but no service connected them to consume a real PR and output an integrated report.
  2. *Source vs Patch Contract*: Diff patches are deltas without context outside modified hunks. Tree-sitter AST parsing requires complete file contents at `base_sha` (for deletions) and `head_sha` (for additions/modifications). The existing importer did not fetch full repository source files.
  3. *Credential Hygiene*: GitHub tokens remained securely encapsulated on the backend within `.env` / `GitHubClient` and were not leaked in request/response payloads or logs.
  4. *AI Provider Verification*: The configured AI provider defaulted to `codebert` with dynamic fallback to `tfidf` when PyTorch/Transformers dependencies are not present, but provider status strings did not explicitly note when fallback occurred.
- **What was implemented**:
  1. Enhanced `GitHubClient` with `get_file_content(owner, repo, file_path, ref)` to fetch complete decoded source files at specific commit SHAs using PyGithub, returning `None` gracefully on 404s, binary content, or removals.
  2. Enhanced `PullRequestDetails` with `base_sha` and `head_sha` tracking.
  3. Created `backend/app/analysis/models.py` defining `PRAnalysisRequest`, `HunkAnalysisDetail`, `FileAnalysisReport`, and `PRAnalysisReport`.
  4. Created `ChangeGuardAnalysisService` (`backend/app/analysis/service.py`):
     - Parses file diffs into structured `DiffHunk` instances.
     - Retrieves full old/new source files from GitHub via `head_sha` and `base_sha` for Python files (`.py`), skipping non-Python or binary files.
     - Performs Tree-sitter AST extraction on complete files and maps entities to hunks using `EntityHunkMapper`.
     - Explicitly records file-level and PR-level limitations if source is unavailable, non-Python, or binary (e.g. `"Full repository source could not be retrieved from GitHub API; entity mapping limited to diff hunk line ranges."`).
     - Executes `IntentAnalyzer` per hunk to assign `EXPLAINED`, `UNEXPLAINED`, or `UNCERTAIN` labels, similarity scores, confidence scores, explanations, and model provider diagnostics.
  5. Updated `FallbackModelProvider` so `provider_name` dynamically reports its operational status (e.g., `"tfidf [fell back from codebert]"`), clearly distinguishing CodeBERT inference from TF-IDF fallback results.
  6. Exposed endpoints in `backend/app/api/v1/analysis.py`:
     - `POST /api/v1/analyze/pull-request`
     - `GET /api/v1/analyze/pull-request/{owner}/{repo}/{pr_number}`
  7. Added 5 integration tests in `backend/tests/test_analysis_service.py` covering:
     - End-to-end analysis with full source and Tree-sitter entity mapping.
     - Fallback handling when repository source is unavailable from GitHub.
     - Graceful skipping of non-Python / binary files with explicit limitations noted.
     - Error handling for nonexistent repositories / PRs (404 mapping).
     - Full API endpoint validation with `TestClient`.
- **Files changed**:
  - `backend/app/github/client.py` (Modified)
  - `backend/app/github/models.py` (Modified)
  - `backend/app/github/importer.py` (Modified)
  - `backend/app/intent/factory.py` (Modified)
  - `backend/app/analysis/__init__.py` (Created)
  - `backend/app/analysis/models.py` (Created)
  - `backend/app/analysis/service.py` (Created)
  - `backend/app/api/v1/analysis.py` (Created)
  - `backend/app/api/v1/router.py` (Modified)
  - `backend/tests/conftest.py` (Modified)
  - `backend/tests/test_analysis_service.py` (Created)
  - `docs/API.md` (Updated)
  - `docs/ARCHITECTURE.md` (Updated)
  - `docs/DEVELOPMENT_LOG.md` (Updated)
- **Tests added**:
  - `test_analysis_service_full_pipeline_with_source`: Validates end-to-end hunk classification and entity mapping with source fetched.
  - `test_analysis_service_source_unavailable_graceful_limitation`: Validates limitation reporting when source cannot be retrieved.
  - `test_analysis_service_skips_non_python_source_fetch`: Validates non-Python files (YAML, Markdown) are diff-analyzed with limitation flags.
  - `test_analysis_service_propagates_not_found_error`: Validates 404 propagation on missing PRs.
  - `test_api_analyze_pull_request_post_and_get`: Validates HTTP 200 response on `POST` and `GET` analysis endpoints.
- **Current status**:
  End-to-end integration audit complete. Analysis pipeline operational. 46/46 automated tests passing in 2.28s. Live inference verified on GitHub PRs.

---

### Entry: 2026-10-19 - Part 1: Provider Wiring Fix & Part 2: Milestone 5 Change & Dependency Graph

- **Date**: 2026-10-19
- **Task**: Fix AI provider wiring from API through service, factory, and intent analyzer to ensure `provider_name='tfidf'` invokes real TF-IDF similarity. Implement Milestone 5: Change & Dependency Graph using NetworkX.
- **What was implemented**:
  1. **Part 1 — Provider Selection & Attribution**:
     - Identified root cause of mock provider usage: `AI_PROVIDER` was defaulted to `"mock"` in config and `.env` from Milestone 1 placeholders, and `PRAnalysisRequest` / `analyze_pull_request` did not accept or route `provider_name`.
     - Updated `PRAnalysisRequest` and `POST /api/v1/analyze/pull-request` to accept optional `provider_name`.
     - Updated `GET /api/v1/analyze/pull-request/{owner}/{repo}/{pr_number}` to accept optional `provider` query parameter.
     - Updated `ChangeGuardAnalysisService` to instantiate `IntentAnalyzer(provider_name=provider_name)` when specified, correctly routing to `create_model_provider`.
     - Updated `create_model_provider` so `mock` and `tfidf` are never wrapped in unnecessary fallbacks, and added eager availability checking to `FallbackModelProvider` so that when `codebert` is requested without `torch` installed, it immediately switches to `tfidf` with clear attribution `"tfidf [fell back from codebert]"`.
     - Updated default in `config.py` and `.env` to `AI_PROVIDER=tfidf` and `AI_MODEL=tfidf-word-v1`.
     - Added unit and API regression tests verifying `tfidf` computes real non-zero cosine similarity with sub-word token expansion, while `mock` remains available for deterministic testing.
  2. **Part 2 — Milestone 5 Change and Dependency Graph**:
     - Created `backend/app/graph/models.py` defining `NodeType` (`FILE`, `CLASS`, `FUNCTION`, `METHOD`, `UNKNOWN`), `EdgeType` (`CONTAINS`, `IMPORTS`, `CALLS`), `GraphNode`, `GraphEdge`, `ImpactPath`, `ImpactedEntity`, and `ChangeGraphReport`.
     - Created `backend/app/graph/graph_builder.py` using `networkx.DiGraph`:
       - Constructs file nodes and entity nodes from Tree-sitter `ParseResult` objects.
       - Adds `CONTAINS` edges for file-to-entity and class-to-method containment.
       - Adds `IMPORTS` edges resolving module/file imports across parsed files.
       - Adds `CALLS` edges resolving call sites to local and imported target entities.
       - Unresolved external imports (e.g. standard library, external packages) and unparsed/binary files are tracked in limitations without inventing false graph edges.
       - Implemented `compute_impact(changed_entity_ids, max_depth=5)` performing BFS traversal over reverse call, import, and containment edges to identify downstream impacted entities and files.
       - Generates explainable impact propagation paths: e.g. `changed function -> called by caller -> contained in file`.
       - Safe cycle prevention using per-source visited tracking to handle recursive calls without infinite loops.
     - Integrated `change_graph: Optional[ChangeGraphReport]` into `PRAnalysisReport` and `ChangeGuardAnalysisService` without breaking any existing API fields.
     - Added 6 focused tests in `backend/tests/test_change_graph.py` and API test in `backend/tests/test_analysis_service.py`.
- **Files changed**:
  - `backend/app/core/config.py` (Modified)
  - `.env` (Modified)
  - `backend/requirements.txt` (Modified - added `networkx>=3.0.0`)
  - `backend/app/intent/factory.py` (Modified)
  - `backend/app/intent/intent_analyzer.py` (Modified)
  - `backend/app/analysis/models.py` (Modified)
  - `backend/app/analysis/service.py` (Modified)
  - `backend/app/api/v1/analysis.py` (Modified)
  - `backend/app/graph/__init__.py` (Created)
  - `backend/app/graph/models.py` (Created)
  - `backend/app/graph/graph_builder.py` (Created)
  - `backend/tests/test_analysis_service.py` (Modified)
  - `backend/tests/test_change_graph.py` (Created)
  - `docs/API.md` (Updated)
  - `docs/ARCHITECTURE.md` (Updated)
  - `docs/DEVELOPMENT_LOG.md` (Updated)
- **Current status**:
  Milestone 5 complete. 58/58 automated tests passing cleanly in 2.51s. Real TF-IDF inference verified. NetworkX change and dependency graph fully operational with explainable downstream impact paths.

---

### Entry: 2026-10-20 - Milestone 6: Impact Analysis & Risk Ranking

- **Date**: 2026-10-20
- **Task**: Implement Milestone 6: Impact Analysis and Risk Ranking. Multi-factor risk evaluation (LOW, MEDIUM, HIGH), relationship verification (CONFIRMED_STATIC, POTENTIAL, UNKNOWN), explainable high-risk impact paths, per-file/per-entity risk breakdown, and non-breaking API integration.
- **What was implemented**:
  1. **Impact and Risk Data Models** (`backend/app/impact/models.py`):
     - `RiskLevel` Enum: `LOW`, `MEDIUM`, `HIGH`.
     - `RelationshipConfidence` Enum: `CONFIRMED_STATIC` (direct distance-1 call/import/containment AST relationship), `POTENTIAL` (transitive distance >= 2 downstream paths), and `UNKNOWN` (unresolved internal imports, missing source, or syntax error blind spots).
     - `RiskFactor`: Captures factor name, risk level, normalized score (0.0 to 1.0), human-readable description, and concrete supporting evidence facts.
     - `EntityRiskDetail`: Per-entity risk tier, min distance, dependent callers count, dependent files count, impact paths, and specific rationale.
     - `FileRiskDetail`: Per-file risk tier, churn volume (additions, deletions, hunks), directly changed entities, downstream impacted entities, and file factors.
     - `PRRiskAssessment`: Overall PR risk tier, composite normalized score, executive summary, explicit `high_risk_reasons`, explainable `primary_impact_paths`, relationship category counts, and static analysis limitations.
  2. **Risk Ranking Engine** (`backend/app/impact/risk_analyzer.py`):
     - Evaluates four orthogonal risk dimensions:
       a. *Downstream Blast Radius*: True downstream callers (excluding home file containment), external dependent files, and propagation depth.
       b. *Change Scope & Volatility*: Additions, deletions, hunk count, and modified file count.
       c. *Intent Alignment*: Correlation with stated PR intent; unexplained changes with downstream callers elevate risk, while low similarity score alone on isolated leaf functions never triggers HIGH risk.
       d. *Dependency Graph Resolvability*: Unresolved internal imports, syntax errors, and missing source code tracked as analysis blind spots.
     - Enforces explainability: Every HIGH risk PR or entity requires explicit documented reasons and supporting step-by-step impact paths.
     - Cycle safe: Handles circular/recursive function calls gracefully without infinite loops.
  3. **Non-Breaking Pipeline and API Integration**:
     - Updated `FileAnalysisReport` with optional `risk: Optional[FileRiskDetail] = None`.
     - Updated `PRAnalysisReport` with optional `risk_assessment: Optional[PRRiskAssessment] = None`.
     - Integrated `RiskAnalyzer` into `ChangeGuardAnalysisService.analyze_pull_request`, running immediately after graph construction.
     - Preserved 100% backward compatibility for all existing API consumers and schemas.
  4. **Automated Testing**:
     - Created `backend/tests/test_risk_analyzer.py` covering:
       - `test_low_risk_scenario`: Localized change with 0 callers and explained intent is rated LOW.
       - `test_medium_risk_scenario`: Moderate change with direct callers is rated MEDIUM with CONFIRMED_STATIC linkage.
       - `test_high_risk_blast_radius_scenario`: Broad blast radius (>4 callers across multiple files/depth) triggers HIGH risk with primary impact paths.
       - `test_high_risk_unexplained_changes_with_downstream_impact`: Unexplained changes affecting callers triggers HIGH risk.
       - `test_low_similarity_alone_does_not_label_high_risk`: Verifies Requirement 6 that low similarity on leaf functions does NOT label PR as HIGH risk.
       - `test_cycle_safety_during_risk_analysis`: Recursive cycles in call graph terminate safely without hanging.
       - `test_incomplete_graph_and_missing_source_handling`: Missing source and unresolved internal imports elevate uncertainty factors.
       - `test_relationship_confidence_distinction`: Distance 1 is CONFIRMED_STATIC, distance 2 is POTENTIAL.
     - Added `test_api_analyze_pr_includes_risk_assessment` in `backend/tests/test_analysis_service.py` validating end-to-end API payloads.
- **Files changed**:
  - `backend/app/impact/__init__.py` (Created)
  - `backend/app/impact/models.py` (Created)
  - `backend/app/impact/risk_analyzer.py` (Created)
  - `backend/app/analysis/models.py` (Modified)
  - `backend/app/analysis/service.py` (Modified)
  - `backend/tests/test_risk_analyzer.py` (Created)
  - `backend/tests/test_analysis_service.py` (Modified)
  - `docs/API.md` (Updated)
  - `docs/ARCHITECTURE.md` (Updated)
  - `docs/DEVELOPMENT_LOG.md` (Updated)
- **Current status**:
  Milestone 6 complete. 67/67 automated tests passing cleanly in 3.53s. Multi-factor risk ranking, explainable impact paths, and relationship categorization fully operational.

---

### Entry: 2026-10-20 - Milestone 7: Regression Test Selection & Cost Audit

- **Date**: 2026-10-20
- **Task**: Part A: Cost and architecture audit (verifying external API usage, ensuring 100% local deterministic algorithms, confirming TF-IDF default with zero hosted LLM calls). Part B: Implement Milestone 7: Regression Test Selection.
- **What was implemented**:
  1. **Cost & Architecture Audit**:
     - Audited all PR analysis flows: verified zero hosted LLM API calls are made during routine analysis.
     - GitHub REST API calls are read-only (`PyGithub`) using existing token authentication.
     - Intent analysis runs on local TF-IDF vectorization with sub-word token expansion (zero API tokens, zero external latency/cost).
     - Confirmed `settings.AI_PROVIDER="tfidf"`; mocks are never silently substituted and are used strictly when requested or in unit tests.
  2. **Regression Test Selection Data Models** (`backend/app/testing/models.py`):
     - `TestPriority` Enum: `P0_CRITICAL` (direct verification of changed code), `P1_HIGH` (distance-1 impacted callers or module import), `P2_MEDIUM` (transitive callers or naming heuristics), `P3_LOW` (module/directory correspondence). Added `__test__ = False` to prevent pytest discovery warnings.
     - `TestMatchType` Enum: `STATIC_CALL`, `STATIC_IMPORT`, `TRANSITIVE_GRAPH`, `NAMING_HEURISTIC`.
     - `SelectedTestCase`: Holds test ID, function/class name, file, priority tier, deterministic score ($0.0 \dots 1.0$), match type, relationship confidence, linked entity IDs, evidence strings, and suggested test execution command.
     - `TestSelectionReport`: Aggregates discovered vs selected test counts, priority breakdown (critical, high, medium, low), executive summary, selection strategy, recommended test cases, and limitations.
  3. **Regression Test Selector Engine** (`backend/app/testing/selector.py`):
     - Discovers test files (`test_*.py`, `*_test.py`, `tests/`) and test entities (`def test_*`, `class Test*`).
     - Correlates tests with modified and impacted code using:
       - Confirmed direct AST call sites (`STATIC_CALL`).
       - Downstream dependency graph propagation calls (`TRANSITIVE_GRAPH`).
       - Static module imports (`STATIC_IMPORT`).
       - Transparent symbol and file naming heuristics (`NAMING_HEURISTIC`).
     - Ranks tests using local deterministic scoring.
     - Never executes arbitrary PR code automatically; provides safe suggested CLI commands (`pytest <path> -k <name>`).
  4. **Non-Breaking API Integration**:
     - Updated `PRAnalysisReport` with optional `test_selection: Optional[TestSelectionReport] = None`.
     - Integrated `RegressionTestSelector` into `ChangeGuardAnalysisService.analyze_pull_request`.
     - Added repository test file candidate discovery via `get_file_content` for modified components when source fetching is enabled.
     - Preserved 100% backward compatibility for all existing API endpoints and schemas.
  5. **Automated Testing**:
     - Created `backend/tests/test_test_selector.py` covering:
       - `test_selector_direct_ast_call_critical`: Direct AST call to modified entity ranked P0_CRITICAL.
       - `test_selector_impacted_entity_call_high`: Direct call to downstream impacted caller ranked P1_HIGH.
       - `test_selector_symbol_naming_heuristic`: Symbol-level naming convention match.
       - `test_selector_static_import_of_module`: Module-level import match ranked P1_HIGH.
       - `test_selector_file_naming_heuristic`: File-level naming heuristic ranked P2_MEDIUM.
       - `test_selector_no_tests_discovered`: Repositories with zero tests handled gracefully.
       - `test_selector_missing_or_unparsed_source`: Unparsed files handled gracefully in limitations.
     - Added `test_api_analyze_pr_includes_test_selection` in `backend/tests/test_analysis_service.py` validating end-to-end API payloads.
- **Files changed**:
  - `backend/app/testing/__init__.py` (Created)
  - `backend/app/testing/models.py` (Created)
  - `backend/app/testing/selector.py` (Created)
  - `backend/app/analysis/models.py` (Modified)
  - `backend/app/analysis/service.py` (Modified)
  - `backend/tests/test_test_selector.py` (Created)
  - `backend/tests/test_analysis_service.py` (Modified)
  - `docs/API.md` (Updated)
  - `docs/ARCHITECTURE.md` (Updated)
  - `docs/DEVELOPMENT_LOG.md` (Updated)
- **Current status**:
  Milestone 7 complete. 75/75 automated tests passing cleanly in 2.81s. Targeted regression test selection fully operational with zero hosted LLM API token consumption.

---

### Entry: 2026-10-20 - Milestone 8: Automatic GitHub PR Monitoring

- **Date**: 2026-10-20
- **Task**: Implement Milestone 8: Automatic local GitHub PR polling worker with persistent state tracking, retry logic, duplicate suppression, and API rate-limit awareness.
- **What was implemented**:
  1. **Background Polling Worker (`backend/app/monitoring/poller.py`)**:
     - Created `PRPollingWorker` running as a controlled background daemon thread.
     - Implemented rate limit pre-flight checking: queries GitHub API rate limits before each cycle and skips execution if quota is critically low (< 5 remaining).
     - Polling interval is fully configurable (`MONITORING_POLL_INTERVAL_SECONDS`, default 60s) and disabled by default (`MONITORING_ENABLED_BY_DEFAULT=false`).
     - Duplicate suppression: compares incoming PR `head.sha` with the recorded `head_sha` in local state. If unchanged, analysis is skipped to avoid redundant processing.
     - Revision re-analysis: if a PR receives a new commit (head SHA changes), re-analysis triggers automatically.
     - Resilient error handling & retries: transitions failed analyses with error message and incremented retry count up to `MAX_PROCESSING_RETRIES` (3) before transitioning to `FAILED`.
  2. **Thread-Safe Persistent State Store (`backend/app/monitoring/state_store.py`)**:
     - Created `MonitoringStateStore` writing atomically to `data/monitoring_state.json` using temporary file creation and atomic OS replacement.
     - Tracks registered repositories (`RepoConfig`) and PR records (`PRStateRecord`) across restarts.
  3. **REST Management Endpoints (`backend/app/api/v1/monitoring.py`)**:
     - `GET /api/v1/monitoring/status`: Returns worker health, running state, and repository counts.
     - `POST /api/v1/monitoring/start` & `POST /api/v1/monitoring/stop`: Worker lifecycle controls.
     - `POST /api/v1/monitoring/poll`: Trigger immediate on-demand polling cycle.
     - `GET`, `POST`, `DELETE /api/v1/monitoring/repositories`: Monitored repo management.
     - `GET /api/v1/monitoring/prs`: List tracked PR records with owner/repo/status filters.
     - `POST /api/v1/monitoring/prs/{owner}/{repo}/{pr_number}/reanalyze`: Force re-analysis.
  4. **GitHub Client Enhancements (`backend/app/github/client.py`)**:
     - Added `get_pull_requests(owner, repo, state, sort, direction)` with pagination limit.
     - Added `get_rate_limit_info()`.
     - Added `post_pull_request_comment(owner, repo, pr_number, body)`.

---

### Entry: 2026-10-20 - Milestone 9: Local Dashboard and Safe GitHub Reporting

- **Date**: 2026-10-20
- **Task**: Implement Milestone 9: Local dashboard single-page frontend and safe GitHub reporting.
- **What was implemented**:
  1. **Zero-Dependency Local Dashboard (`backend/app/static/index.html`)**:
     - Built a complete, modern responsive single-page application served directly by FastAPI at `/` and `/dashboard`.
     - Uses native HTML, modern CSS glassmorphism, responsive grid, and Vanilla JavaScript with zero npm/node dependencies or build steps.
     - Features:
       - Real-time monitoring status badges (worker running/stopped, tracked PRs, active repos).
       - Worker controls: Start, Stop, Trigger Poll button with live feedback.
       - Repository manager: Add repository (owner/repo), toggle, delete.
       - PR table: PR number, title, author, branch, status badges (`completed`, `running`, `failed`, `pending`), commit hash, and inspection action.
       - Comprehensive PR Detail Modal:
         - Overall risk assessment badge, score, and summary.
         - Intent classifications and supporting evidence per hunk.
         - Impacted entities, blast radius, and explainable dependency paths.
         - Ranked regression test recommendations with priority badges and suggested commands.
         - Explicit system limitations and failures.
         - Force re-analysis button and safe GitHub comment button.
  2. **Safe Read-Only Reporting Safeguard**:
     - Endpoint `POST /api/v1/monitoring/prs/{owner}/{repo}/{pr_number}/comment` enforces `ENABLE_GITHUB_REPORTING=false` default.
     - Rejects comment posting safely when disabled, returning an informational explanation without remote write modifications.

---

### Entry: 2026-10-20 - Milestone 10: Evaluation, Reliability, and Deployment

- **Date**: 2026-10-20
- **Task**: Implement Milestone 10: Repeatable empirical evaluation framework, integration reliability tests, documentation, and deployment guides.
- **What was implemented**:
  1. **Benchmark Fixture Suite (`backend/app/evaluation/benchmark_fixtures.py`)**:
     - Implemented 4 curated architectural pull request scenarios with ground-truth labels:
       - `PR-101`: Focused bugfix (auth token validation in `refresh_token`), isolated caller, unit test.
       - `PR-102`: Scope creep (database optimization + stealth unannounced analytics tracker modification).
       - `PR-103`: Ambiguous/empty PR description with utility formatting modification.
       - `PR-104`: Core architectural change (`DatabasePool.execute`), downstream caller propagation, test suite targets.
  2. **Repeatable Evaluator (`backend/app/evaluation/evaluator.py`)**:
     - Executes all benchmark scenarios through the genuine ChangeGuard AST parser, diff engine, TF-IDF intent analyzer, dependency graph, risk engine, and test selector.
     - Calculates empirical metrics:
       - Intent Classification: Precision, Recall, F1 per class (`EXPLAINED`, `UNEXPLAINED`, `UNCERTAIN`), Confusion Matrix, False Positives/Negatives.
       - Dependency Impact: Precision, Recall, F1 for impacted entity identification.
       - Regression Test Selection: Target test coverage (Hit Rate), Precision.
       - Risk Alignment Rate: Percentage of PR scenarios whose risk tier matches ground truth.
     - Generates publication-ready Markdown and structured JSON reports.
  3. **Evaluation CLI Script (`scripts/run_evaluation.py`)**:
     - Executable CLI runner writing reports to `docs/EVALUATION_REPORT.md` and `data/evaluation_report.json`.
  4. **Automated Reliability Tests**:
     - `backend/tests/test_monitoring.py` (10 tests): State store persistence, atomic file writing, polling loop, duplicate suppression, commit update re-analysis, retry exhaustion, rate limit pausing, API endpoints, reporting permission guards, and dashboard HTML serving.
     - `backend/tests/test_evaluation.py` (2 tests): Fixture integrity and automated evaluation metrics verification.
  5. **Verification**:
     - Full repository test suite: **87 passed, 1 warning in 6.75s**.
     - Benchmark evaluation output: **100% test coverage hit-rate, 100% impact recall, 100% risk alignment**.

---

### Entry: 2026-10-20 - On-Demand Real GitHub Pull Request Workflow & Verification

- **Date**: 2026-10-20
- **Task**: Prepare ChangeGuard for on-demand testing against real GitHub pull requests, bridge on-demand CLI/API workflows, persist on-demand runs to local state store, and add mocked + live GitHub integration tests.
- **What was implemented**:
  1. **On-Demand PR Analysis CLI (`scripts/analyze_pr.py`)**:
     - Built a standalone terminal runner that accepts `--owner`, `--repo`, `--pr`, and optional `--provider` and `--json`.
     - Fetches PR metadata and changed-file diffs from GitHub.
     - Runs the complete ChangeGuard pipeline: Tree-sitter code parsing, TF-IDF intent engine, change & dependency graph, multi-factor risk assessment, and targeted regression test selection.
     - Automatically saves the analysis result into `data/monitoring_state.json` so directly analyzed PRs appear instantly in the local dashboard without requiring background worker polling.
     - Displays formatted terminal output with risk tier, blast radius, intent hunk evidence, and recommended test execution commands.
  2. **API State Store Persistence Integration (`backend/app/api/v1/analysis.py`)**:
     - Integrated `_save_to_state_store` in both `POST /api/v1/analyze/pull-request` and `GET /api/v1/analyze/pull-request/{owner}/{repo}/{pr_number}`.
     - Guarantees on-demand analyses triggered via curl, Swagger, or the dashboard's "Quick Direct PR Analysis" card are persistently recorded.
  3. **Automated On-Demand Workflow Tests (`backend/tests/test_on_demand_workflow.py`)**:
     - Added `test_on_demand_analysis_with_mocked_github` verifying full pipeline execution with simulated GitHub responses.
     - Added `test_on_demand_api_persists_to_state_store` verifying FastAPI endpoints persist state records.
     - Added `test_real_public_github_pr_live_analysis` validating live network execution against `octocat/Hello-World` PR #1.
  4. **Live Verification**:
     - Tested live GitHub API authentication and rate limit quota (4,950+ requests remaining).
     - Verified live end-to-end analysis on `octocat/Hello-World` PR #1 and `pallets/flask` PR #5000.
     - Verified full test suite: **90 passed, 1 warning in 7.27s**.




