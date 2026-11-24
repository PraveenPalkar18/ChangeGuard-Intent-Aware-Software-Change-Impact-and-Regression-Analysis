# ChangeGuard: AI Models & Semantic Provider Specification

## 1. Overview
ChangeGuard provides a modular AI intent-analysis layer that evaluates whether code diff hunks align with the stated developer intent from Pull Request titles, descriptions, and commit logs.

The architecture decouples the deterministic algorithmic similarity baseline (TF-IDF character/word n-gram cosine similarity) from hosted LLM reasoning layers, supporting:
1. **Groq Cloud LPU Provider** (Recommended): High-speed LPU inference with Meta's `llama-3.3-70b-versatile` or Qwen's `qwen/qwen3.8-27b`, offering sub-second response times and native JSON schema extraction.
2. **Google Gemini API Provider**: Hosted multi-modal LLM reasoning with `gemini-2.5-flash` / `gemini-3.8-flash` via official `google-genai` SDK.
3. **Local Deterministic Baseline**: `tfidf-word-v1` (100% local, zero external network dependency, compound identifier sub-token expansion).
4. **Mock Provider**: Offline deterministic token-overlap provider for automated test suites.

---

## 2. Model & Provider Inventory

| Provider Key | Primary Model ID | Architecture / SDK | Purpose | Inference Latency | Network Dependency |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **`groq`** (Recommended) | `llama-3.3-70b-versatile` | Groq Python SDK (`groq`) | Ultra-fast LPU inference, structured intent classification | ~250ms | Groq Cloud REST API |
| **`gemini`** | `gemini-2.5-flash` | Google GenAI SDK (`google-genai`) | Multi-modal reasoning with JSON schema | ~1200ms | Google AI Studio REST API |
| **`tfidf`** (Default fallback) | `tfidf-word-v1` | scikit-learn TF-IDF + Heuristic AST Rules | Local deterministic baseline & guaranteed offline fallback | ~5ms | None (100% Local) |
| **`mock`** | `mock-jaccard` | In-memory token overlap | Offline automated unit/integration testing | <1ms | None |

---

## 3. Groq Cloud LPU Integration Guide (Recommended)

ChangeGuard natively integrates with **Groq Cloud API** leveraging high-speed Language Processing Unit (LPU) hardware for ultra-low latency pull request intent analysis.

### 3.1 Supported Models
- **`llama-3.3-70b-versatile`** (Default / Recommended): Meta's 70B parameter model with 128k context, strong code comprehension, and native JSON mode.
- **`qwen/qwen3.8-27b`**: High reasoning density model optimized for technical analysis.
- **`llama-3.1-8b-instant`**: 8B parameter model tracking ~560 tokens/second, optimized for rapid turnaround.

### 3.2 Obtaining a Free Groq API Key
1. Navigate to the **Groq Console**: [https://console.groq.com/](https://console.groq.com/)
2. Sign up or log in.
3. Go to **API Keys**: [https://console.groq.com/keys](https://console.groq.com/keys)
4. Click **Create API Key**.
5. Copy the generated key (starts with `gsk_...`).

### 3.3 Configuring Environment Variables
Add the following to your local `.env` file (never commit `.env` to Git):
```dotenv
AI_PROVIDER=groq
GROQ_API_KEY=gsk_your_actual_key_here
AI_MODEL_NAME=llama-3.3-70b-versatile
AI_TIMEOUT_SECONDS=30
AI_MAX_OUTPUT_TOKENS=2048
AI_FALLBACK_ENABLED=true
AI_CACHE_ENABLED=true
```

Or configure temporarily in PowerShell:
```powershell
$env:AI_PROVIDER="groq"
$env:GROQ_API_KEY="gsk_your_actual_key_here"
$env:AI_MODEL_NAME="llama-3.3-70b-versatile"
```

### 3.4 Verification Smoke Test
ChangeGuard includes a dedicated smoke test that verifies real Groq API connectivity without leaking tokens:
```powershell
python scripts/groq_smoke_test.py
```
- Displays masked key (e.g. `gsk_...abcd`).
- Tests real structured JSON intent classification.
- Exits 0 on success, 1 on failure or unconfigured key.

---

## 4. Google Gemini API Integration Guide

### 4.1 Obtaining a Gemini API Key
1. Navigate to **Google AI Studio**: [https://aistudio.google.com/](https://aistudio.google.com/)
2. Sign in with your Google account.
3. Click **Get API key** $\rightarrow$ **Create API key**.
4. Copy the generated key (e.g. `AQ...` or `AIza...`).

### 4.2 Configuring Environment Variables
Add to your local `.env` file:
```dotenv
AI_PROVIDER=gemini
AI_MODEL_NAME=gemini-2.5-flash
GEMINI_API_KEY=your_actual_gemini_api_key_here
AI_TIMEOUT_SECONDS=30
AI_MAX_OUTPUT_TOKENS=2048
AI_FALLBACK_ENABLED=true
AI_CACHE_ENABLED=true
```

### 4.3 Verification Smoke Test
```powershell
python scripts/gemini_smoke_test.py
```

---

## 5. Local Deterministic TF-IDF Baseline Engine

When no external API key is provided or when offline, ChangeGuard uses `TFIDFSimilarityProvider`:
1. **Compound Identifier Splitting**: Extracts sub-tokens from `camelCase` (e.g. `getUserProfile` $\rightarrow$ `get`, `user`, `profile`) and `snake_case` (e.g. `auth_token_refresh` $\rightarrow$ `auth`, `token`, `refresh`).
2. **Sub-Token Cosine Vectorization**: Calculates term-frequency inverse-document-frequency vectors between stated PR intent text and modified diff lines.
3. **Deterministic Classification Rules**:
   - $\text{Cosine Similarity} \ge 0.40$ or direct entity keyword match $\rightarrow$ `EXPLAINED`.
   - $\text{Cosine Similarity} \le 0.15$ with no lexical overlap $\rightarrow$ `UNEXPLAINED`.
   - $0.15 < \text{Cosine Similarity} < 0.40$ or empty PR body $\rightarrow$ `UNCERTAIN`.

---

## 6. Security, Privacy & Free-Tier Guardrails

### 6.1 Automated Secret Redaction
Before any diff text or commit log is transmitted to external AI endpoints, `redact_sensitive_tokens()` scans the input for credentials:
- GitHub tokens (`ghp_...`, `github_pat_...`)
- Groq API keys (`gsk_...`)
- Google API keys (`AIza...`, `AQ....`)
- Generic bearer tokens (`bearer ...`, `sk-...`)
- Private RSA / EC cryptographic keys (`-----BEGIN PRIVATE KEY-----`)

Matches are replaced with `[REDACTED_SECRET]` to prevent token leakage.

### 6.2 Prompt Injection Defense
Diffs and PR descriptions are treated strictly as untrusted data within system prompts. Prompts explicitly prohibit executable instructions found in diff lines from overriding classification logic.

### 6.3 Resilient Fallback Architecture
When `AI_FALLBACK_ENABLED=true`:
- If an external provider experiences network failure, timeout, quota exhaustion (HTTP 429), or invalid credentials, `FallbackModelProvider` transparently falls back to local `tfidf`.
- The analysis result documents the fallback in `processing_limitations` without crashing the application.
