# ChangeGuard: API Documentation

Base URL: `http://localhost:8000/api/v1`

Interactive API Docs:
- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`

---

## 1. Health Endpoints

### `GET /health` / `GET /api/v1/health`
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

## 2. GitHub Endpoints

### `POST /api/v1/github/pull-request/import`
Imports a Pull Request given repository coordinates and PR number.

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
  "title": "Test2",
  "description": "PR body markdown...",
  "author": "TedSpinks",
  "state": "closed",
  "created_at": "2023-02-23T22:03:29+00:00",
  "updated_at": "2023-02-24T18:12:00+00:00",
  "merged_at": null,
  "base_branch": "main",
  "head_branch": "test2",
  "commits_count": 40,
  "changed_files_count": 6,
  "total_additions": 78,
  "total_deletions": 155,
  "commits": [
    {
      "sha": "82a6d535...",
      "message": "Add example ci pipeline",
      "author_name": "ted-cdw",
      "author_email": "ted@example.com",
      "timestamp": "2023-02-23T21:40:00+00:00"
    }
  ],
  "files": [
    {
      "filename": ".github/workflows/flaskr-ci.yaml",
      "status": "added",
      "additions": 64,
      "deletions": 0,
      "changes": 64,
      "patch": "@@ -0,0 +1,64 @@\n+name: Build and Test\n...",
      "raw_url": "https://github.com/pallets/flask/raw/...",
      "previous_filename": null
    }
  ]
}
```

**Error Responses**:
- `401 Unauthorized`: Invalid or expired GitHub credentials.
- `404 Not Found`: Repository or Pull Request does not exist.
- `422 Unprocessable Entity`: Request body validation error (e.g. negative PR number or missing fields).
- `429 Too Many Requests`: GitHub API rate limit reached.
- `502 Bad Gateway`: GitHub API upstream error.

---

### `GET /api/v1/github/pull-request/{owner}/{repo}/{pr_number}`
Convenience endpoint fetching the exact same payload as `POST /import`, callable directly from a browser or simple GET request.

**Parameters**:
- `owner` (path, string): Repository owner
- `repo` (path, string): Repository name
- `pr_number` (path, integer): Pull Request number

---

### `GET /api/v1/github/rate-limit`
Returns remaining GitHub rate limit statistics.

**Response `200 OK`**:
```json
{
  "limit": 60,
  "remaining": 58,
  "reset_time": "2026-10-08T07:33:13+00:00"
}
```
*(With `GITHUB_TOKEN` configured, the limit increases to 5,000 requests/hour).*

---

## 3. Analysis Endpoints

These endpoints perform full end-to-end ChangeGuard analysis: GitHub PR ingestion -> unified diff parsing -> Tree-sitter AST entity mapping (where Python source is available) -> AI intent classification per hunk -> structured explainability report.

### `POST /api/v1/analyze/pull-request`
Runs an end-to-end ChangeGuard analysis for a specified GitHub Pull Request.

**Request Body**:
```json
{
  "owner": "pallets",
  "repo": "flask",
  "pr_number": 5000,
  "provider_name": "tfidf"
}
```
*Note: `provider_name` is optional (defaults to `"codebert"` with automatic graceful fallback to `"tfidf"` if PyTorch/Transformers are not installed).*

**Response `200 OK`**:
```json
{
  "owner": "pallets",
  "repo": "flask",
  "pr_number": 5000,
  "title": "Test2",
  "author": "TedSpinks",
  "base_sha": "abc123456789...",
  "head_sha": "def987654321...",
  "model_provider": "tfidf [fell back from codebert]",
  "files_analyzed": 6,
  "total_hunks": 12,
  "explained_hunks": 8,
  "unexplained_hunks": 2,
  "uncertain_hunks": 2,
  "pr_intent_summary": "Test2\n\nAdd example ci pipeline...",
  "files": [
    {
      "filename": "app/billing.py",
      "status": "modified",
      "patch_available": true,
      "source_available": true,
      "ast_entities_found": 2,
      "hunks_count": 1,
      "hunks": [
        {
          "hunk_index": 1,
          "header": "@@ -3,3 +3,5 @@ class BillingService:",
          "old_start_line": 3,
          "new_start_line": 3,
          "change_type": "modified",
          "matched_entity_id": "app/billing.py::BillingService.calculate_discount",
          "matched_entity_name": "calculate_discount",
          "matched_entity_type": "method",
          "association_type": "enclosing",
          "classification": "EXPLAINED",
          "confidence": 0.85,
          "similarity_score": 0.32,
          "reason": "Hunk changes align with stated PR intent. Direct symbol mention found: ['calculate_discount'].",
          "evidence": ["Direct reference to entity 'calculate_discount' in stated intent."],
          "limitations": [],
          "model_used": "tfidf-baseline",
          "provider_used": "tfidf"
        }
      ],
      "limitations": [],
      "risk": {
        "filename": "app/billing.py",
        "risk_level": "MEDIUM",
        "risk_score": 0.45,
        "directly_changed_entities": 1,
        "impacted_entities_count": 0,
        "hunks_count": 1,
        "added_lines": 3,
        "deleted_lines": 1,
        "unexplained_hunks_count": 0,
        "uncertain_hunks_count": 0,
        "reasons": [
          "Modified entities affect 1 downstream dependents."
        ],
        "factors": [
          {
            "name": "Code Volatility",
            "level": "LOW",
            "score": 0.15,
            "description": "Small localized diff.",
            "evidence": ["4 lines changed in 1 hunks"]
          }
        ]
      }
    }
  ],
  "change_graph": {
    "total_nodes": 6,
    "total_edges": 5,
    "changed_entities": [
      "entity:app/billing.py::BillingService.calculate_discount"
    ],
    "impacted_entities_count": 1,
    "impacted_files_count": 1,
    "impacted_entities": [
      {
        "node_id": "entity:app/checkout.py::process_order",
        "name": "process_order",
        "entity_type": "function",
        "file_path": "app/checkout.py",
        "min_distance": 1,
        "impact_paths": [
          {
            "target_id": "entity:app/checkout.py::process_order",
            "target_name": "process_order",
            "target_type": "function",
            "target_file": "app/checkout.py",
            "path_nodes": [
              "entity:app/billing.py::BillingService.calculate_discount",
              "entity:app/checkout.py::process_order"
            ],
            "path_description": "app/billing.py::calculate_discount -> called by app/checkout.py::process_order",
            "distance": 1,
            "impact_reason": "Calls changed function/method 'app/billing.py::calculate_discount'"
          }
        ]
      }
    ],
    "impacted_files": [
      "app/checkout.py"
    ],
    "graph_limitations": []
  },
  "risk_assessment": {
    "overall_risk_level": "MEDIUM",
    "overall_risk_score": 0.45,
    "summary": "MEDIUM RISK (Score: 0.45) — Moderate change scope affecting 1 downstream entity callers across 1 dependent files. Standard targeted regression tests recommended.",
    "high_risk_reasons": [],
    "primary_impact_paths": [],
    "confirmed_relationships_count": 1,
    "potential_relationships_count": 0,
    "unknown_relationships_count": 0,
    "risk_factors": [
      {
        "name": "Downstream Blast Radius",
        "level": "MEDIUM",
        "score": 0.35,
        "description": "PR modifications propagate to downstream caller(s) or dependent files.",
        "evidence": [
          "1 downstream impacted entities",
          "1 downstream impacted files"
        ]
      },
      {
        "name": "Change Scope & Volatility",
        "level": "LOW",
        "score": 0.05,
        "description": "Low change volume localized to few lines.",
        "evidence": ["4 lines changed across 1 hunk(s)"]
      },
      {
        "name": "Intent Alignment",
        "level": "LOW",
        "score": 0.1,
        "description": "All changed hunks align with stated Pull Request intent.",
        "evidence": ["Zero unexplained or anomalous hunks identified."]
      },
      {
        "name": "Dependency Graph Resolvability",
        "level": "LOW",
        "score": 0.05,
        "description": "All repository internal imports and code entities fully resolved in AST.",
        "evidence": ["100% internal imports and AST entities statically verified."]
      }
    ],
    "entity_risks": [
      {
        "node_id": "entity:app/billing.py::BillingService.calculate_discount",
        "name": "calculate_discount",
        "entity_type": "method",
        "file_path": "app/billing.py",
        "is_directly_changed": true,
        "risk_level": "MEDIUM",
        "risk_score": 0.35,
        "relationship_type": "CONFIRMED_STATIC",
        "min_distance": 0,
        "dependent_entities_count": 1,
        "dependent_files_count": 1,
        "impact_paths": [
          {
            "target_id": "entity:app/checkout.py::process_order",
            "target_name": "process_order",
            "target_type": "function",
            "target_file": "app/checkout.py",
            "path_nodes": [
              "entity:app/billing.py::BillingService.calculate_discount",
              "entity:app/checkout.py::process_order"
            ],
            "path_description": "app/billing.py::calculate_discount -> called by app/checkout.py::process_order",
            "distance": 1,
            "impact_reason": "Calls changed function/method 'app/billing.py::calculate_discount'"
          }
        ],
        "reasons": [
          "Direct callers affected: 1 downstream entity dependent(s)."
        ],
        "factors": [
          {
            "name": "Downstream Blast Radius",
            "level": "MEDIUM",
            "score": 0.35,
            "description": "Direct modification affects known downstream caller(s).",
            "evidence": ["1 downstream entity callers in 1 file(s)"]
          }
        ]
      }
    ],
    "file_risks": [
      {
        "filename": "app/billing.py",
        "risk_level": "MEDIUM",
        "risk_score": 0.45,
        "directly_changed_entities": 1,
        "impacted_entities_count": 0,
        "hunks_count": 1,
        "added_lines": 3,
        "deleted_lines": 1,
        "unexplained_hunks_count": 0,
        "uncertain_hunks_count": 0,
        "reasons": [
          "Modified entities affect 1 downstream dependents."
        ],
        "factors": [
          {
            "name": "Code Volatility",
            "level": "LOW",
            "score": 0.15,
            "description": "Small localized diff.",
            "evidence": ["4 lines changed in 1 hunks"]
          }
        ]
      }
    ],
    "limitations": [
      "Static dependency analysis reflects AST call sites and explicit imports; dynamic runtime dispatch, reflection, or monkey-patching cannot be statically confirmed.",
      "Risk scores are heuristic indicators based on structural blast radius, change scope, and intent alignment; they do not represent calibrated probability of production regression."
    ]
  },
  "test_selection": {
    "total_tests_discovered": 1,
    "selected_tests_count": 1,
    "critical_count": 1,
    "high_count": 0,
    "medium_count": 0,
    "low_count": 0,
    "summary": "Selected 1 targeted regression test(s) (1 critical, 0 high, 0 medium) covering changed and downstream impacted code.",
    "recommended_tests": [
      {
        "test_id": "tests/test_billing.py::test_calculate_discount",
        "test_name": "test_calculate_discount",
        "test_file": "tests/test_billing.py",
        "priority": "P0_CRITICAL",
        "score": 0.95,
        "match_type": "STATIC_CALL",
        "relationship_confidence": "CONFIRMED_STATIC",
        "linked_entities": [
          "entity:app/billing.py::BillingService.calculate_discount"
        ],
        "evidence": [
          "Direct AST invocation of modified entity 'calculate_discount' at line 14."
        ],
        "suggested_command": "pytest tests/test_billing.py -k test_calculate_discount"
      }
    ],
    "selection_strategy": "AST Call Graph Traversal + Static Imports + Transparent Naming Heuristics",
    "limitations": [
      "Test selection is based on static AST call sites, imports, and naming conventions; dynamic pytest fixtures, mock patches, or parameterized test cases without static call sites may not be identified.",
      "ChangeGuard provides test recommendations for local or CI execution; arbitrary PR code is never executed automatically."
    ]
  },
  "processing_limitations": []
}
```

**Test Selection Priorities**:
- `P0_CRITICAL`: Directly verifies modified code via confirmed static AST call sites or direct symbol-level targeting with module import.
- `P1_HIGH`: Verifies direct downstream impacted entities (distance 1 in dependency graph) or imports the modified module.
- `P2_MEDIUM`: Verifies transitive callers (distance >= 2 hops) or matches via file/module naming conventions.
- `P3_LOW`: Broader directory or module-level correspondence.

**Test Match Types**:
- `STATIC_CALL`: Confirmed direct AST function/method invocation within test body.
- `STATIC_IMPORT`: Confirmed static module or symbol import in test file.
- `TRANSITIVE_GRAPH`: Invokes downstream caller linked through multi-hop dependency graph.
- `NAMING_HEURISTIC`: Established via transparent naming convention matching (e.g. `test_billing.py` -> `billing.py` or `test_foo` -> `foo`).

**Risk Assessment Levels**:
- `LOW`: Localized change with zero or minimal downstream callers. Churn is low, all hunks are explained, and graph resolution is complete.
- `MEDIUM`: Moderate change scope affecting 1-3 downstream callers/files, moderate churn, uncertain intent alignment, or minor internal dependency blind spots.
- `HIGH`: Broad downstream blast radius (>=4 downstream entities, >=2 dependent files, or propagation depth >=3), unexplained changes directly affecting downstream callers, or high diff churn with downstream propagation. Accompanied by concrete `high_risk_reasons` and explainable `primary_impact_paths`.

**Relationship Verification Categories**:
- `CONFIRMED_STATIC`: Directly verified in AST (direct call site, explicit module import, enclosing parent definition) at distance 1.
- `POTENTIAL`: Transitive / indirect downstream propagation (distance >= 2 hops) or heuristic correlation.
- `UNKNOWN`: Unresolved internal imports, missing AST source, or syntax errors where static dependents cannot be guaranteed.

**Classification Labels**:
- `EXPLAINED`: The hunk's changes (code tokens, enclosing entities, docstrings) align with the PR title/description or directly reference documented symbols.
- `UNEXPLAINED`: The hunk changes code semantically orthogonal to stated PR intent.
- `UNCERTAIN`: PR description is empty/vague, or similarity score falls in the boundary region requiring human review.

**Error Responses**:
- `401 Unauthorized`: GitHub credentials invalid.
- `404 Not Found`: Repository or PR not found on GitHub.
- `422 Unprocessable Entity`: Invalid request parameters.
- `429 Too Many Requests`: GitHub API rate limit exceeded.

---

### `GET /api/v1/analyze/pull-request/{owner}/{repo}/{pr_number}`
Convenience GET endpoint executing the same analysis pipeline, callable directly from a browser or curl.

**Query Parameters**:
- `provider` (optional, string): AI model provider (`"tfidf"`, `"codebert"`, or `"mock"`). Defaults to `"tfidf"`.

---

## 4. Monitoring, State Tracking, and Dashboard Endpoints (Milestones 8 & 9)

### `GET /` & `GET /dashboard`
Serves the ChangeGuard local dashboard single-page web interface.

**Response `200 OK`**: `text/html`

---

### `GET /api/v1/monitoring/status`
Returns the real-time operational status of the background polling worker.

**Response `200 OK`**:
```json
{
  "is_running": false,
  "poll_interval_seconds": 60,
  "monitored_repos": [
    {
      "owner": "pallets",
      "repo": "flask",
      "enabled": true,
      "poll_interval_seconds": 60
    }
  ],
  "last_poll_time": "2026-10-20T10:00:00Z",
  "total_prs_tracked": 12,
  "pending_count": 0,
  "running_count": 0,
  "completed_count": 11,
  "failed_count": 1
}
```

---

### `POST /api/v1/monitoring/start`
Starts the background polling worker daemon thread.

**Response `200 OK`**:
```json
{
  "status": "started",
  "is_running": true
}
```

---

### `POST /api/v1/monitoring/stop`
Stops the background polling worker daemon thread cleanly.

**Response `200 OK`**:
```json
{
  "status": "stopped",
  "is_running": false
}
```

---

### `POST /api/v1/monitoring/poll`
Triggers an immediate manual polling cycle across all active monitored repositories.

**Response `200 OK`**:
```json
{
  "status": "poll_completed",
  "summary": {
    "timestamp": "2026-10-20T10:05:00Z",
    "repos_checked": 2,
    "prs_discovered": 5,
    "prs_analyzed": 1,
    "prs_skipped": 4,
    "errors": []
  }
}
```

---

### `GET /api/v1/monitoring/repositories`
Lists all repositories currently configured for polling.

---

### `POST /api/v1/monitoring/repositories`
Registers or updates a repository in the local persistent store.

**Request Body**:
```json
{
  "owner": "pallets",
  "repo": "flask",
  "enabled": true,
  "poll_interval_seconds": 60
}
```

---

### `DELETE /api/v1/monitoring/repositories/{owner}/{repo}`
Removes a repository from monitoring.

---

### `GET /api/v1/monitoring/prs`
Lists tracked PR state records. Supports filtering by query parameters.

**Query Parameters**:
- `owner` (optional, string): Filter by repository owner
- `repo` (optional, string): Filter by repository name
- `status` (optional, string): Filter by state (`"pending"`, `"running"`, `"completed"`, `"failed"`)

---

### `GET /api/v1/monitoring/prs/{owner}/{repo}/{pr_number}`
Retrieves persistent state and the full cached analysis report for a specific pull request.

---

### `POST /api/v1/monitoring/prs/{owner}/{repo}/{pr_number}/reanalyze`
Forces an immediate re-analysis of the PR, bypassing duplicate suppression.

---

### `POST /api/v1/monitoring/prs/{owner}/{repo}/{pr_number}/comment`
Posts the Markdown analysis summary to the GitHub PR as an issue comment.

> [!IMPORTANT]
> **Safe Read-Only Guard:** GitHub writing is disabled by default. If `ENABLE_GITHUB_REPORTING` is `false` in `.env`, this endpoint returns a safe status response without modifying the remote repository.
