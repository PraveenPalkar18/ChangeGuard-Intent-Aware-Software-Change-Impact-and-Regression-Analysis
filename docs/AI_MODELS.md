# ChangeGuard: AI Models Specification

## 1. Overview
ChangeGuard requires an AI layer to compare stated developer intent (from Pull Request titles, descriptions, and commit logs) with concrete code modifications (extracted unified diff hunks and Tree-sitter code entities).

Rather than binding the system to a single proprietary LLM or fragile API, ChangeGuard establishes a modular provider abstraction (`AIModelProvider`) with configurable backends and automatic fallback handling.

---

## 2. Model Inventory & Current Configuration

| Attribute | Baseline (Current Active) | Pretrained Embedding | Mock (Testing) |
| :--- | :--- | :--- | :--- |
| **Model ID** | `tfidf-baseline` | `microsoft/codebert-base` | `mock-jaccard` |
| **Provider** | `tfidf` | `codebert` | `mock` |
| **Model Version** | `v1.0.0` (unigram + sub-token expansion) | Hugging Face Transformers (`v1`) | `v1.0.0` |
| **Model Purpose** | Lexical TF-IDF cosine similarity baseline | Dense contextual token representation | Offline unit test verification |
| **Input Format** | Natural language text + code representation | Tokenized sequence (max 512 tokens) | Normalized token strings |
| **Output Format** | Similarity score `[0.0, 1.0]` | Cosine similarity `[0.0, 1.0]` | Jaccard overlap `[0.0, 1.0]` |
| **Context Window** | Unlimited | 512 subword tokens | Unlimited |
| **Hardware Reqs** | Low CPU, < 100MB RAM | 8GB RAM, CUDA GPU recommended | Minimal CPU, < 10MB RAM |
| **Inference Cost** | Free ($0.00 / query) | Free local inference ($0.00) | Free ($0.00) |
| **API Limits** | None (Local execution) | None (Local weights) | None |

---

## 3. Environment Variables & Model Selection
Model selection is decoupled from business logic and governed entirely by environment variables or application configuration:

```env
# AI Intent Engine Configuration
AI_PROVIDER=tfidf
AI_MODEL=tfidf-baseline
AI_API_KEY=
```

To enable the CodeBERT provider:
```env
AI_PROVIDER=codebert
AI_MODEL=microsoft/codebert-base
```

---

## 4. Input & Output Contract

### Input Format
The `IntentAnalyzer` constructs two inputs for the provider:
1. **PR Intent (`PRContext.full_intent_text`)**:
   ```
   "Fix invalid discount rate crash. Adds validation check for discount rate parameters in billing logic."
   ```
2. **Code Representation (`HunkContext.code_representation`)**:
   ```
   "function calculate_discount Compute discount with rate validation. price rate if rate < 0 or rate > 1: raise ValueError return price * (1 - rate)"
   ```

### Output Format
The provider outputs a float `similarity_score` in `[0.0, 1.0]`. The `IntentAnalyzer` translates this score into a structured `HunkIntentResult`:
```json
{
  "hunk_index": 0,
  "file_path": "app/billing.py",
  "classification": "EXPLAINED",
  "confidence": 0.82,
  "similarity_score": 0.4851,
  "reason": "Change in 'app/billing.py' shows strong semantic alignment with the stated PR intent. Direct reference to symbol 'calculate_discount' confirmed.",
  "evidence": [
    "Entity 'calculate_discount' is explicitly referenced in the PR intent text.",
    "Model similarity score: 0.4851 (thresholds: explained >= 0.20, unexplained < 0.05)"
  ],
  "limitations": [
    "Semantic similarity alone does not constitute mathematical proof of intent alignment.",
    "Static analysis cannot detect dynamic runtime or indirect call linkages."
  ],
  "model_used": "tfidf-baseline",
  "provider_used": "tfidf"
}
```

---

## 5. Classification Logic & Thresholds

ChangeGuard enforces three distinct classification states:
- **`EXPLAINED`** (`similarity >= 0.20` or direct identifier match):
  The hunk contains symbols or concepts directly stated in the PR title, body, or commits.
- **`UNCERTAIN`** (`0.05 <= similarity < 0.20`, or missing PR description):
  Crucial architectural safeguard: **Semantic similarity alone must NOT be treated as proof of an unexplained change.** A legitimate refactor or cross-component change may have low lexical overlap. When in doubt, the engine classifies as `UNCERTAIN` to prompt reviewer inspection rather than falsely raising alarms.
- **`UNEXPLAINED`** (`similarity < 0.05` with no identifier matches, no commit linkages, and not a test file):
  The change exhibits zero detectable semantic or symbol correlation with the stated intent.

---

## 6. Pretrained Model Evaluation (CodeBERT & UniXcoder)

### Evaluation Analysis
- **CodeBERT (`microsoft/codebert-base`)**:
  - Pretrained on CodeSearchNet across 6 programming languages including Python.
  - Generates dense 768-dimensional contextual embeddings using RoBERTa architecture.
  - **Advantage**: Better captures semantic synonyms (e.g. associating "remove" with `del` or `.pop()`).
  - **Limitation**: 512 token truncation window limits large multi-line hunks; requires PyTorch (~2GB disk) and slower CPU inference (~150ms vs ~2ms for TF-IDF).
- **UniXcoder (`microsoft/unixcoder-base`)**:
  - Unified cross-modal pretraining utilizing AST structure.
  - Similar trade-offs to CodeBERT.

---

## 7. Model Fallback Mechanism

If the primary configured provider fails (e.g. Hugging Face weights unavailable or CUDA out of memory), the `FallbackModelProvider` automatically diverts inference to the local secondary provider (e.g. `tfidf`) and logs a diagnostic warning. It **never silently fabricates artificial results**.

---

## 8. Limitations & Future Work
1. **Context Window**: Transformer models truncate after 512 tokens. Future milestones will implement sliding-window hunk chunking.
2. **Fine-Tuning**: Pretrained models are zero-shot evaluators. Fine-tuning on labeled commit-PR datasets will be explored in future evaluation milestones once ground truth datasets are established.
