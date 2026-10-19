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
      "limitations": []
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
  "processing_limitations": []
}
```

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
- `provider` (optional, string): AI model provider (`"tfidf"`, `"codebert"`, or `"mock"`). Defaults to `"codebert"`.
