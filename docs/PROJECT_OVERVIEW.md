# ChangeGuard: Project Overview

## 1. Project Identity
- **Project Name**: ChangeGuard
- **Project Title**: Intent-Aware Software Change Impact and Regression Analysis
- **Goal**: A production-grade, deployable AI-powered software engineering system that connects developer intent with code modifications, identifies unexplained changes, tracks multi-language dependency impact, and plans targeted regression tests.

---

## 2. Core Problem & Motivation
In modern code review workflows, developers submit Pull Requests containing:
1. High-level intent expressed in PR titles and markdown descriptions.
2. Concrete code modifications scattered across diffs and commits.

Reviewers face significant cognitive load attempting to manually answer four critical questions:
- **Why was the change made?** (Stated intent in the PR description and commit logs)
- **What actually changed?** (Diff hunks, added/removed logic, refactored functions/classes)
- **What could the change affect?** (Direct callers, indirect modules, downstream dependencies)
- **What should be tested?** (Targeted regression tests rather than slow, costly blanket test runs)

Existing code review assistants focus on surface-level style, security heuristics, or generic generative summarization. **ChangeGuard does not replace general code review or linters.** Instead, its primary value proposition is:

> *"Connect why a change was made, what actually changed, what the change may affect, and what should be tested."*

---

## 3. High-Level Pipeline

```
GitHub Pull Request (PR Title, Description, Commits, Diffs)
                         ↓
             Diff-Hunk Extraction & Normalization
                         ↓
  AI Intent Analysis (Explained / Unexplained / Uncertain)
  [Groq LPU / Google Gemini / Local TF-IDF Cosine Baseline]
                         ↓
   Universal Code Parsing & Multi-Language AST Extraction
   [Python, JavaScript, TypeScript, Go, Java, Rust, C# + Fallback]
                         ↓
        Change & Dependency Graph (NetworkX MultiDiGraph)
                         ↓
   Blast Radius & Impact Analysis (Direct & Transitive Callers)
                         ↓
    Targeted Regression Test Recommendation (Ranked P0-P3)
                         ↓
   Interactive Web Dashboard (SVG DAG Visual Graph & 3-Pillar Cards)
```

---

## 4. Key Capabilities & Scope

### 4.1 Universal Multi-Language AST Parsing
- Native Tree-sitter AST extraction across 7 premier programming languages:
  - **Python** (`.py`)
  - **JavaScript** (`.js`, `.jsx`, `.mjs`, `.cjs`)
  - **TypeScript** (`.ts`, `.tsx`)
  - **Go** (`.go`)
  - **Java** (`.java`)
  - **Rust** (`.rs`)
  - **C#** (`.cs`)
- Generic regex/heuristic fallback parser for Ruby, PHP, Kotlin, Swift, Dart, Scala, C/C++, Shell, and other languages.
- Extracts classes, standalone functions, methods, call sites, and import statements with full error tolerance and 1-indexed line mappings.

### 4.2 Multi-Provider AI Intent Engine
- **Groq LPU Provider**: Ultra-fast inference with `llama-3.3-70b-versatile` or `qwen/qwen3.8-27b` providing structured JSON intent classifications in milliseconds.
- **Google Gemini Provider**: Hosted multi-modal LLM reasoning with `gemini-2.5-flash` and `gemini-3.8-flash` via official `google-genai` SDK.
- **Local TF-IDF Baseline**: 100% deterministic, offline sub-token cosine similarity baseline with compound identifier splitting (`camelCase` and `snake_case`).
- **Resilient Fallback**: Automatic failover to local TF-IDF if external AI APIs encounter network timeouts, quota limits, or invalid keys.
- **Privacy & Security**: Automated secret redaction (`ghp_...`, `gsk_...`, `AIza...`, RSA keys) before prompts leave the local machine.

### 4.3 Change Graph & Blast Radius Traversal
- In-memory directed graph constructed via NetworkX.
- Reverse breadth-first search (BFS) traversing caller and import hierarchies to compute transitive blast radius up to configurable hop depth.
- Clear distinction between confirmed direct static callers (`CONFIRMED_STATIC`, distance 1) and indirect transitive callers (`POTENTIAL`, distance >= 2).

### 4.4 Targeted Regression Test Selection
- Automatic discovery of multi-language test suites across frameworks (`pytest`, `jest`, `mocha`, `go test`, `junit`, `nunit`, `cargo test`).
- Prioritizes candidate tests into ranked tiers (`P0_CRITICAL`, `P1_HIGH`, `P2_MEDIUM`, `P3_LOW`).
- Generates ready-to-run CLI commands without executing arbitrary code, maintaining strict local safety.

### 4.5 Interactive Web Dashboard & Visual Graph
- Real-time single-page application served directly by FastAPI with zero Node.js/npm dependencies.
- **3-Pillar Intent Cards**: Highlights Explained, Unexplained, and Uncertain changes with clear "Why" reasoning and collapsible technical details.
- **Interactive SVG DAG Visual Graph**: Topological 4-column visualization (`Changed File` $\rightarrow$ `Modified Entity` $\rightarrow$ `Impacted Caller` $\rightarrow$ `Test Suite`) with interactive node inspection.
- **Automatic Local Monitoring**: Background daemon polling GitHub repositories with duplicate commit suppression (`head_sha` tracking) and rate-limit guardrails.

---

## 5. Milestone History & Status
1. **Milestone 1**: Backend foundation, GitHub client, environment configuration, read-only PR importer, typed exceptions, unit/integration test suite. *(Completed)*
2. **Milestone 2**: Unified diff parser, hunk data structures, 1-indexed line number mappings. *(Completed)*
3. **Milestone 3**: Tree-sitter code parsing & entity-hunk association. *(Completed)*
4. **Milestone 4**: Modular AI Intent Analyzer abstraction, TF-IDF baseline, and model fallback orchestrator. *(Completed)*
5. **Milestone 5**: Change & Dependency Graph modeling using NetworkX. *(Completed)*
6. **Milestone 6**: Impact propagation engine & multi-factor blast radius calculation. *(Completed)*
7. **Milestone 7**: Regression test recommendation planner with priority ranking. *(Completed)*
8. **Milestone 8**: Background PR polling worker, atomic persistent state store, rate-limit awareness. *(Completed)*
9. **Milestone 9**: Local single-page dashboard and safe read-only GitHub reporting safeguards. *(Completed)*
10. **Milestone 10**: Repeatable empirical benchmark evaluation framework, multi-language universal parser (`UniversalCodeParser`), Groq & Gemini cloud providers, interactive SVG DAG visualization, and 151 verified tests. *(Completed)*
