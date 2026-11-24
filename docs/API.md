# ChangeGuard: API Documentation

Base URL: `http://localhost:8000/api/v1`

Interactive API Documentation:
- **Swagger UI**: `http://localhost:8000/docs`
- **ReDoc**: `http://localhost:8000/redoc`
- **Web Dashboard**: `http://localhost:8000/` or `http://localhost:8000/dashboard`

---

## 1. Health Endpoints

### `GET /health` or `GET /api/v1/health`
Checks whether the backend server is operational.

**Response `200 OK`**:
```json
{
  "status": "healthy",
  "service": "ChangeGuard",
  "version": "0.1.0",
  "environment": "development"
}
```

---

## 2. GitHub Ingestion Endpoints

### `POST /api/v1/github/pull-request/import`
Imports a Pull Request given repository coordinates and PR number using read-only GitHub API integration.

**Request Body**:
```json
{
  "owner": "pallets",
  "repo": "flask",
  "pr_number": 5000
}
```

**Response `200 OK`**:
```json
{
  "owner": "pallets",
  "repo": "flask",
  "pr_number": 5000,
  "title": "Support modern Python versions",
  "description": "PR body markdown...",
  "author": "developer-username",
  "state": "open",
  "created_at": "2026-02-23T22:03:29+00:00",
  "updated_at": "2026-02-24T18:12:00+00:00",
  "merged_at": null,
  "base_branch": "main",
  "head_branch": "feature/modern-py",
  "commits_count": 3,
  "changed_files_count": 2,
  "total_additions": 45,
  "total_deletions": 12,
  "commits": [
    {
      "sha": "82a6d535...",
      "message": "Update type hints and call signature",
      "author_name": "developer",
      "author_email": "dev@example.com",
      "timestamp": "2026-02-23T21:40:00+00:00"
    }
  ],
  "files": [
    {
      "filename": "flask/app.py",
      "status": "modified",
      "additions": 35,
      "deletions": 10,
      "changes": 45,
      "patch": "@@ -120,7 +120,10 @@\n-def handle_request():\n+def handle_request(req: Request) -> Response:\n",
      "raw_url": "https://github.com/pallets/flask/raw/...",
      "previous_filename": null
    }
  ]
}
```

**Error Responses**:
- `401 Unauthorized`: Missing or invalid `GITHUB_TOKEN`.
- `404 Not Found`: Repository or Pull Request does not exist.
- `422 Unprocessable Entity`: Request payload validation failure.
- `429 Too Many Requests`: GitHub API rate limit exhausted.
- `502 Bad Gateway`: GitHub API upstream network error.

---

### `GET /api/v1/github/pull-request/{owner}/{repo}/{pr_number}`
Convenience GET endpoint providing the same response as `POST /import`.

---

### `GET /api/v1/github/rate-limit`
Returns GitHub API rate-limit statistics.

**Response `200 OK`**:
```json
{
  "limit": 5000,
  "remaining": 4982,
  "reset_time": "2026-10-21T18:00:00+00:00"
}
```

---

## 3. End-to-End PR Analysis Endpoints

Full pipeline execution: GitHub ingestion $\rightarrow$ diff parsing $\rightarrow$ multi-language AST extraction (`UniversalCodeParser`) $\rightarrow$ AI intent evaluation per hunk $\rightarrow$ dependency graph traversal $\rightarrow$ regression test selection $\rightarrow$ persistence in state store.

### `POST /api/v1/analyze/pull-request`

**Request Body**:
```json
{
  "owner": "pallets",
  "repo": "flask",
  "pr_number": 5000,
  "fetch_source_files": true,
  "provider_name": "groq"
}
```
*`provider_name` options: `"groq"` (recommended), `"gemini"`, `"tfidf"` (local fallback), `"mock"`.*

**Response `200 OK` (`PRAnalysisReport`)**:
```json
{
  "owner": "pallets",
  "repo": "flask",
  "pr_number": 5000,
  "title": "Update request routing and type annotations",
  "description": "This PR refactors handle_request to accept typed request objects.",
  "author": "developer-username",
  "state": "open",
  "base_branch": "main",
  "head_branch": "feature/modern-py",
  "ai_provider": "groq",
  "ai_model": "llama-3.3-70b-versatile",
  "total_files_analyzed": 2,
  "total_hunks_analyzed": 3,
  "explained_count": 2,
  "unexplained_count": 1,
  "contradictory_count": 0,
  "uncertain_count": 0,
  "overall_intent_summary": "2 hunks clearly align with stated PR intent. 1 hunk appears unannounced or out of scope.",
  "files": [
    {
      "filename": "flask/app.py",
      "status": "modified",
      "patch_available": true,
      "source_available": true,
      "ast_entities_found": 14,
      "hunks_count": 2,
      "hunks": [
        {
          "hunk_index": 0,
          "header": "@@ -120,7 +120,10 @@",
          "old_start_line": 120,
          "new_start_line": 120,
          "change_type": "modified",
          "matched_entity_id": "flask/app.py::Flask.handle_request",
          "matched_entity_name": "handle_request",
          "matched_entity_type": "method",
          "association_type": "enclosing",
          "classification": "EXPLAINED",
          "confidence": 0.94,
          "similarity_score": 0.88,
          "reason": "Change modifies handle_request signature as described in PR title and description.",
          "apparent_purpose": "Add Request type annotation to handle_request method",
          "evidence": [
            "PR description explicitly mentions handle_request",
            "Added lines introduce Request type hint"
          ],
          "contradiction_signals": [],
          "missing_context": [],
          "uncertainty_score": 0.05,
          "limitations": [],
          "model_used": "llama-3.3-70b-versatile",
          "provider_used": "groq"
        }
      ],
      "limitations": []
    }
  ],
  "change_graph": {
    "total_nodes": 18,
    "total_edges": 24,
    "modified_entities": ["flask/app.py::Flask.handle_request"],
    "impacted_entities": [
      {
        "entity_id": "flask/ctx.py::AppContext.push",
        "entity_name": "push",
        "file_path": "flask/ctx.py",
        "distance": 1,
        "relationship_type": "CONFIRMED_STATIC",
        "shortest_path": ["flask/app.py::Flask.handle_request", "flask/ctx.py::AppContext.push"]
      }
    ],
    "blast_radius_score": 0.35
  },
  "test_selection": {
    "selected_tests": [
      {
        "test_id": "tests/test_basic.py::test_request_dispatching",
        "test_name": "test_request_dispatching",
        "file_path": "tests/test_basic.py",
        "priority": "P0_CRITICAL",
        "selection_source": "STATIC_CALL",
        "suggested_command": "pytest tests/test_basic.py -k test_request_dispatching",
        "target_entity_id": "flask/app.py::Flask.handle_request",
        "reason": "Directly invokes modified method Flask.handle_request"
      }
    ],
    "total_recommended": 1,
    "summary": "1 critical regression test identified across test suites."
  },
  "processing_limitations": []
}
```

---

### `GET /api/v1/analyze/pull-request/{owner}/{repo}/{pr_number}`
Convenience GET shortcut accepting path parameters.

---

## 4. Automatic PR Monitoring & Poller Endpoints

ChangeGuard includes a local background poller that tracks configured GitHub repositories and detects new PR revisions.

### `GET /api/v1/monitoring/status`
Returns poller status, running state, and statistics.

**Response `200 OK`**:
```json
{
  "is_running": true,
  "poll_interval_seconds": 60,
  "monitored_repositories_count": 2,
  "total_tracked_prs": 5,
  "last_poll_time": "2026-10-21T18:05:00+00:00"
}
```

### `POST /api/v1/monitoring/start`
Starts the background polling daemon.

### `POST /api/v1/monitoring/stop`
Stops the background polling daemon gracefully.

### `POST /api/v1/monitoring/poll`
Triggers an immediate on-demand polling cycle across all monitored repositories.

### `GET /api/v1/monitoring/repositories`
Lists all monitored repository configurations.

### `POST /api/v1/monitoring/repositories`
Registers a repository for background polling.

**Request Body**:
```json
{
  "owner": "pallets",
  "repo": "flask",
  "is_active": true
}
```

### `DELETE /api/v1/monitoring/repositories/{owner}/{repo}`
Removes a repository from monitoring.

### `GET /api/v1/monitoring/prs`
Lists all tracked PR records in persistent state store with status, commit hashes, and stored reports.

### `POST /api/v1/monitoring/prs/{owner}/{repo}/{pr_number}/reanalyze`
Forces re-analysis of a specific PR, ignoring commit SHA cache.

### `POST /api/v1/monitoring/prs/{owner}/{repo}/{pr_number}/comment`
Posts ChangeGuard analysis findings as a GitHub comment on the PR. Requires `ENABLE_GITHUB_REPORTING=true` in `.env`; otherwise rejected safely in read-only mode.
