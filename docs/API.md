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
