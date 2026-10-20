# ChangeGuard — System Evaluation Report (Milestone 10)

**Generated:** `2026-10-20T06:00:37.037055+00:00` | **Provider:** `tfidf` | **Fixtures Evaluated:** `4`

## 1. Executive Summary

ChangeGuard was evaluated using a repeatable benchmark suite comprising 4 curated architectural pull request scenarios containing 5 distinct diff hunks with manually verified ground-truth labels for intent, AST dependency relationships, and regression test selection.

| Engine / Capability | Metric | Value | Sample Size / Support |
| :--- | :--- | :--- | :--- |
| **Intent Classification** | Overall Accuracy | **60.0%** | 5 hunks |
| **Intent Classification** | Macro F1-Score | **0.33** | 5 hunks |
| **Dependency Impact** | Impacted Entity Recall | **100.0%** | 6 entities |
| **Dependency Impact** | Impacted Entity Precision | **54.5%** | 11 entities |
| **Test Selection** | Target Test Coverage (Hit Rate) | **100.0%** | 2 expected tests |
| **Risk Assessment** | Risk Tier Alignment | **100.0%** | 4 PR scenarios |

## 2. Intent Classification Breakdown

| Intent Class | Precision | Recall | F1-Score | Ground Truth Support |
| :--- | :--- | :--- | :--- | :--- |
| `EXPLAINED` | 1.00 | 1.00 | 1.00 | 3 |
| `UNEXPLAINED` | 0.00 | 0.00 | 0.00 | 1 |
| `UNCERTAIN` | 0.00 | 0.00 | 0.00 | 1 |

### Confusion Matrix

| Ground Truth \ Predicted | EXPLAINED | UNEXPLAINED | UNCERTAIN |
| :--- | :--- | :--- | :--- |
| **EXPLAINED** | 3 | 0 | 0 |
| **UNEXPLAINED** | 0 | 0 | 1 |
| **UNCERTAIN** | 0 | 1 | 0 |

### Discrepancy Analysis (False Positives / False Negatives)

- **False Negative** in `PR-102` (analytics/tracker.py hunk #0): Expected `UNEXPLAINED`, but classified as `UNCERTAIN`.
- **False Negative** in `PR-103` (utils/formatter.py hunk #0): Expected `UNCERTAIN`, but classified as `UNEXPLAINED`.
## 3. Dependency Graph & Impact Identification

- **Expected Impacted Entities:** 6
- **Predicted Impacted Entities:** 11
- **True Positives:** 6
- **Precision:** 0.55 | **Recall:** 1.00 | **F1-Score:** 0.71
- **Unresolved External Import Blind Spots:** 0

## 4. Regression Test Selection Usefulness

- **Expected Critical Tests:** 2
- **Selected Tests Recommended:** 2
- **Relevant Tests Identified:** 2
- **Target Test Coverage (Hit Rate):** 100.0%

## 5. Explicit System Limitations

- Evaluation was conducted on curated synthetic/real benchmark fixtures representing key architectural scenarios.
- Intent evaluation relies on TF-IDF textual/lexical semantic similarity and entity keyword matching.
- AST and dependency graph extraction is currently fully implemented for Python source files; other languages fall back to file-level tracking.
- Targeted regression test ranking does not execute candidate tests automatically, preserving local execution safety.
- Real-world generalization metrics require continuous sampling across production repository PR streams.