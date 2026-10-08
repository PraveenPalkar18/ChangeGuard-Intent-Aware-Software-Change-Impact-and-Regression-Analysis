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
  Milestone 1 complete. 12/12 automated tests passing cleanly. Live GitHub PR retrieval verified via both CLI and API schemas.

- **Next step**:
  Awaiting user confirmation to proceed to Milestone 2: Diff and Hunk Processing (Unified diff parsing, extraction of individual hunks with old/new line numbers, added/deleted line tracking, and associated code entity mapping).
