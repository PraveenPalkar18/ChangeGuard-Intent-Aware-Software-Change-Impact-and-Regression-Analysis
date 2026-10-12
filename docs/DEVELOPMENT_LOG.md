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
  Awaiting user confirmation to proceed to Milestone 4: Modular AI Intent Analysis Engine (abstraction, model provider, baseline lexical model, code embeddings, hunk classification as EXPLAINED / UNEXPLAINED / UNCERTAIN).
