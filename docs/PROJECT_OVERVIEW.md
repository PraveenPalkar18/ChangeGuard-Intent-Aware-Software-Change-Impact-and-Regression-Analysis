# ChangeGuard: Project Overview

## 1. Project Identity
- **Project Name**: ChangeGuard
- **Project Title**: Intent-Aware Software Change Impact and Regression Analysis
- **Goal**: A production-grade, deployable AI-powered software engineering system that connects developer intent with code modifications, identifies unexplained changes, tracks dependency impact, and plans targeted regression tests.

---

## 2. Core Problem & Motivation
In modern code review workflows, developers submit Pull Requests containing:
1. High-level intent expressed in PR titles and markdown descriptions.
2. Concrete code modifications scattered across diffs and commits.

Reviewers face significant cognitive load attempting to manually answer four critical questions:
- **Why was the change made?** (Stated intent in the PR description)
- **What actually changed?** (Diff hunks, added/removed logic, refactors)
- **What could the change affect?** (Direct and indirect callers, modules, dependencies)
- **What should be tested?** (Targeted regression tests rather than slow blanket test suites)

Existing code review assistants focus on surface-level style, security heuristics, or generative summarization. **ChangeGuard does not replace general code review or linters.** Instead, its primary value proposition is:

> *"Connect why a change was made, what actually changed, what the change may affect, and what should be tested."*

---

## 3. High-Level Pipeline

```
GitHub Pull Request (PR Title, Description, Commits, Diffs)
                         ↓
             Diff-Hunk Extraction & Normalization
                         ↓
     Intent Analysis (Explained / Unexplained / Uncertain)
                         ↓
  Repository Structure & Dependency Graph (Tree-sitter + NetworkX)
                         ↓
             Impact Analysis (Affected Callers & Modules)
                         ↓
     Targeted Regression Test Recommendation (Ranked Test Suite)
                         ↓
          Explainable Final Report & Dashboard
```

---

## 4. MVP Scope
The Minimal Viable Product focuses on:
- Single programming language support: **Python** (reliable AST/Tree-sitter analysis).
- Read-only GitHub integration via REST API (Pull Requests, commits, patches).
- Hunk-level diff parsing and metadata extraction.
- Modular AI Intent Analysis interface supporting pluggable backends (embeddings, models, LLMs) with clean configuration.
- Dependency and call graph modeling using NetworkX.
- Impact propagation and test ranking algorithms.
- Explainable output reports with clear evidence for every classification.
- User authentication, analysis persistence, and an interactive dashboard.

---

## 5. Milestone Roadmap
1. **Milestone 1 (Current)**: Backend foundation, environment configuration, GitHub authentication, read-only PR importer, unit/integration testing with mocks, and initial architecture documentation.
2. **Milestone 2**: Diff & Hunk Parsing Engine (unified diff parser, hunk data structures, line mapping).
3. **Milestone 3**: Code Parsing & Entity Extraction (Python AST & Tree-sitter integration).
4. **Milestone 4**: Pluggable AI Intent Analyzer Abstraction & Baseline Model.
5. **Milestone 5**: Dependency & Change Graph (NetworkX representation).
6. **Milestone 6**: Impact Analysis Engine & Scoring.
7. **Milestone 7**: Regression Test Recommendation Planner.
8. **Milestone 8**: Database Layer (PostgreSQL) & Authentication.
9. **Milestone 9**: Web Interface (React + Tailwind CSS).
10. **Milestone 10**: End-to-End Evaluation, Dockerization, and Deployment.
