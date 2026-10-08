# ChangeGuard

> **Intent-Aware Software Change Impact and Regression Analysis**

ChangeGuard connects **why** a code change was made, **what** actually changed, **what** components may be affected, and **which** regression tests should be executed.

---

## Quickstart Guide

### 1. Prerequisites
- Python 3.10+ (tested on Python 3.12)
- Git

### 2. Environment Setup

Clone repository and create a Python virtual environment:
```powershell
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
```

### 3. Configuration
Copy the sample environment file:
```powershell
cp .env.example .env
```
Optional: Set your `GITHUB_TOKEN` inside `.env` to unlock higher GitHub rate limits (up to 5,000 requests/hour instead of 60 requests/hour for unauthenticated access).

### 4. Running the Tests
Execute the automated test suite:
```powershell
pytest -v
```

### 5. Running the Pull Request Importer

#### Option A: Command-Line Interface (CLI)
You can directly inspect any public or private GitHub Pull Request from the terminal:
```powershell
python scripts/run_importer.py --owner pallets --repo flask --pr 5000
```
Or view the raw structured JSON output:
```powershell
python scripts/run_importer.py --owner octocat --repo Hello-World --pr 1 --json
```

#### Option B: REST API & Interactive Docs
Start the FastAPI server:
```powershell
uvicorn backend.app.main:app --reload --port 8000
```
Open your browser to:
- Interactive Swagger UI: [http://localhost:8000/docs](http://localhost:8000/docs)
- Health Check: [http://localhost:8000/health](http://localhost:8000/health)
- Import PR via GET: `http://localhost:8000/api/v1/github/pull-request/pallets/flask/5000`

---

## Documentation
- [Project Overview](docs/PROJECT_OVERVIEW.md)
- [Architecture Specification](docs/ARCHITECTURE.md)
- [API Documentation](docs/API.md)
- [Development Log](docs/DEVELOPMENT_LOG.md)
