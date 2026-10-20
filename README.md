# ChangeGuard

> **Intent-Aware Software Change Impact and Regression Analysis**

ChangeGuard is a local, lightweight developer intelligence system that bridges **why** a code change was made (PR intent), **what** actually changed (syntactic diff and AST entity mapping), **what** components are impacted (dependency graph & risk ranking), and **which** targeted regression tests should be executed.

---

## Capabilities & Architecture (Milestones M1–M10)

- **M1: GitHub PR Ingestion**: Read-only extraction of PR metadata, commits, and diff hunks.
- **M2: Unified Diff Preprocessor**: Line-accurate delta parsing and added/deleted/context lines segmentation.
- **M3: Tree-sitter Code Parsing**: Grammar-based AST extraction of functions, methods, classes, calls, and imports.
- **M4: Modular AI Intent Engine**: Lightweight, zero-token local TF-IDF cosine similarity provider with sub-word identifier expansion; optional CodeBERT fallback.
- **M5: Change and Dependency Graph**: Multi-hop containment, import, and call graph with downstream impact propagation.
- **M6: Impact Analysis & Risk Ranking**: Multi-factor risk engine (`LOW`, `MEDIUM`, `HIGH`) with explainable evidence paths and blast radius tracking.
- **M7: Targeted Regression Test Selection**: Prioritizes test cases (`P0_CRITICAL` to `P3_LOW`) using AST call sites, static imports, and naming heuristics with zero automatic execution of untrusted code.
- **M8: Automatic GitHub PR Monitoring**: Background polling worker with rate-limit pre-flight checks, atomic state persistence (`data/monitoring_state.json`), retry loops, and commit `head_sha` duplicate suppression.
- **M9: Local Dashboard & Safe Reporting**: Modern, zero-dependency glassmorphism dashboard served directly at `http://localhost:8000/dashboard`. Safe read-only reporting safeguard disabled by default.
- **M10: Repeatable Evaluation Suite**: Benchmark evaluation framework with curated ground-truth scenarios, empirical metrics reporting (precision, recall, F1, test coverage), and discrepancy analysis.

---

## Quickstart Guide

### 1. Prerequisites
- **Operating System**: Windows 10/11 (or Linux/macOS)
- **Python**: Python 3.10 to 3.12 (tested on 3.12.10)
- **PowerShell**: Windows PowerShell 5.1 or PowerShell Core 7+
- **Git**: Installed and available in PATH

### 2. Environment Setup

From a clean PowerShell terminal in the repository root:
```powershell
# 1. Create and activate virtual environment
python -m venv .venv
.\.venv\Scripts\activate

# 2. Upgrade pip and install dependencies
pip install --upgrade pip
pip install -r requirements.txt
```

### 3. Configuration

```powershell
# Copy the template configuration
cp .env.example .env
```

Edit `.env` (optional):
- **`GITHUB_TOKEN`**: Paste a personal access token (fine-grained with read-only access to Public Repositories) to increase API rate limits from 60 req/hr to 5,000 req/hr.
- **`MONITORING_ENABLED_BY_DEFAULT`**: Set to `true` if you want the background worker to start automatically on server launch (default: `false`).
- **`ENABLE_GITHUB_REPORTING`**: Set to `true` only if you explicitly want to allow ChangeGuard to post Markdown analysis reports as PR comments on GitHub (default: `false` for safe read-only operation).

---

## Running the Application

### 1. Execute the Full Automated Test Suite
Run the 87 automated unit and integration tests:
```powershell
pytest -v
```

### 2. Run the Benchmark Evaluation Suite (Milestone 10)
Execute the repeatable benchmark evaluator on curated architectural pull request fixtures:
```powershell
python scripts/run_evaluation.py
```
This prints the metrics table to your terminal and updates `docs/EVALUATION_REPORT.md` and `data/evaluation_report.json`.

### 3. Run On-Demand Analysis via CLI (Direct GitHub PR Inspection)
Inspect and analyze any public or private GitHub PR directly from your terminal:
```powershell
python scripts/analyze_pr.py --owner pallets --repo flask --pr 5000
```
Or output raw structured JSON:
```powershell
python scripts/analyze_pr.py --owner octocat --repo Hello-World --pr 1 --json
```
*Note: Any PR analyzed via the CLI is automatically cached and saved to `data/monitoring_state.json` so you can also view it interactively in the web dashboard.*

### 4. Start the Backend & Local Dashboard
Launch the FastAPI server (serves both REST API and Local Dashboard UI):
```powershell
uvicorn backend.app.main:app --reload --port 8000
```

Open your browser to:
- **Interactive Local Dashboard**: [http://localhost:8000/dashboard](http://localhost:8000/dashboard) or [http://localhost:8000/](http://localhost:8000/)
- **Interactive Swagger API Docs**: [http://localhost:8000/docs](http://localhost:8000/docs)
- **System Health Check**: [http://localhost:8000/health](http://localhost:8000/health)

---

## Practical Local Demonstration Procedure

Follow these step-by-step instructions to test ChangeGuard with a real GitHub pull request:

### Step 1: Start the Dashboard
```powershell
uvicorn backend.app.main:app --port 8000
```
Open [http://localhost:8000/dashboard](http://localhost:8000/dashboard) in your browser.

### Step 2: Add a Repository to Monitor
1. In the **Monitored Repositories** card on the dashboard, enter:
   - **Owner**: `pallets`
   - **Repository**: `flask`
2. Click **+ Add Repository**.
3. Notice that `pallets/flask` appears immediately in the active monitoring table.

### Step 3: Trigger PR Detection & Analysis
1. Click **Trigger Poll Now** in the header controls (or click **Start Poller** to let the background daemon poll automatically).
2. The worker contacts the GitHub API, checks remaining rate limits, discovers recent open pull requests, and processes them through:
   - Git unified diff parsing.
   - Tree-sitter AST extraction for modified Python files.
   - TF-IDF Intent classification comparing the PR description with changed hunks.
   - Dependency graph propagation and blast radius analysis.
   - Multi-factor risk ranking (`LOW`, `MEDIUM`, `HIGH`).
   - Targeted regression test recommendation with suggested CLI commands.
3. The table refreshes showing the detected pull requests with status badges (`completed`), author, commit hash, and timestamp.

### Step 4: Inspect Deep PR Intelligence
1. Click **Inspect Analysis** on any completed pull request row in the table.
2. The interactive modal opens, presenting:
   - **Executive Risk Assessment**: Overall risk level badge, composite risk score, and plain-language summary.
   - **Intent Analysis**: Classifications for every diff hunk (`EXPLAINED`, `UNEXPLAINED`, `UNCERTAIN`) with similarity scores and explicit evidence tokens.
   - **Dependency Graph & Blast Radius**: Impacted entities, caller distances, and step-by-step propagation paths.
   - **Targeted Regression Tests**: Ranked list of recommended tests (`P0_CRITICAL` to `P3_LOW`) with matching criteria (`STATIC_CALL`, `STATIC_IMPORT`, `NAMING_HEURISTIC`) and the exact suggested test command.
   - **Analysis Boundaries & Limitations**: Transparent declaration of AST coverage and unverified dynamic runtime assumptions.

### Step 5: Duplicate Suppression & Re-Analysis Verification
- Click **Trigger Poll Now** a second time.
- Observe that the PR is skipped with zero redundant re-analysis because the commit `head_sha` is identical.
- Click **Re-analyze** in the detail modal to verify on-demand analysis refresh.

---

## Troubleshooting & Safe Operation

| Problem | Cause | Solution |
| :--- | :--- | :--- |
| `HTTP 429: GitHub rate limit exceeded` | Unauthenticated GitHub requests exceeded 60/hr. | Add a free GitHub token to `.env` (`GITHUB_TOKEN=ghp_...`) to get 5,000 requests/hr. ChangeGuard will automatically detect it. |
| Poller shows `Rate limit critical (< 5 remaining)` | Rate limit budget is exhausted. | The worker pauses automatically to prevent account suspension. Wait for the hourly reset or configure a token. |
| GitHub comment fails with `403 / Disabled` | Write permissions are disabled by default. | This is intentional safe behavior. Set `ENABLE_GITHUB_REPORTING=true` in `.env` only if you explicitly intend to post comments. |
| Tree-sitter AST shows `file_level` on non-Python | Language grammar is not Python. | Non-Python source files fall back gracefully to file-level tracking without crashing. |

---

## Documentation Index
- [Architecture Specification](docs/ARCHITECTURE.md)
- [API Documentation](docs/API.md)
- [Milestone 10 Evaluation Report](docs/EVALUATION_REPORT.md)
- [Development Log](docs/DEVELOPMENT_LOG.md)
- [Data Pipeline & Diff Parser](docs/DATA_PIPELINE.md)
- [Code Parsing & Tree-sitter](docs/CODE_PARSING.md)
- [AI Models & Intent Engine](docs/AI_MODELS.md)
