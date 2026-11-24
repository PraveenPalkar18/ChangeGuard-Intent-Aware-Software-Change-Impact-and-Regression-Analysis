"""ChangeGuard: Gemini API Semantic Intent Checking Smoke Test.

Executes a controlled, non-sensitive synthetic PR intent analysis using
the configured Google Gemini API provider and reports real results.

Usage:
    python scripts/gemini_smoke_test.py
"""
import os
import sys
import time

# Ensure project root is in sys.path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from backend.app.core.config import settings
from backend.app.intent.models import PRContext, HunkContext, UncertaintyLevel
from backend.app.preprocessing.models import DiffHunk, DiffLine, DiffLineType
from backend.app.repository.models import CodeEntity, CodeEntityType
from backend.app.intent.semantic_engine import GeminiSemanticEngine, redact_sensitive_tokens


def mask_key(key: str) -> str:
    """Masks an API key for safe display (e.g., AQ...GVA)."""
    if not key:
        return "(none)"
    if len(key) <= 8:
        return "***"
    return f"{key[:4]}...{key[-4:]}"


def build_synthetic_pr() -> tuple[PRContext, HunkContext]:
    """Builds a non-sensitive synthetic PR test case."""
    pr_context = PRContext(
        pr_title="fix: normalize product names before validation",
        pr_description="Ensure all product names are stripped of leading/trailing whitespace and rejected if empty."
    )

    diff_lines = [
        DiffLine(line_type=DiffLineType.CONTEXT, content="def validate_product(name: str, price: float):", old_line_number=1, new_line_number=1),
        DiffLine(line_type=DiffLineType.DELETED, content="    if not name:", old_line_number=2),
        DiffLine(line_type=DiffLineType.ADDED, content="    cleaned_name = name.strip()", new_line_number=2),
        DiffLine(line_type=DiffLineType.ADDED, content="    if not cleaned_name:", new_line_number=3),
        DiffLine(line_type=DiffLineType.CONTEXT, content="        raise ValueError('Product name cannot be empty')", old_line_number=3, new_line_number=4),
        DiffLine(line_type=DiffLineType.CONTEXT, content="    return {'name': cleaned_name, 'price': price}", old_line_number=4, new_line_number=5),
    ]

    hunk = DiffHunk(
        header="@@ -1,4 +1,5 @@",
        old_start_line=1,
        old_line_count=4,
        new_start_line=1,
        new_line_count=5,
        lines=diff_lines,
    )

    entity = CodeEntity(
        id="func:validate_product",
        name="validate_product",
        entity_type=CodeEntityType.FUNCTION,
        file_path="backend/app/services/product_service.py",
        start_line=1,
        end_line=20,
    )

    hunk_context = HunkContext(
        file_path="backend/app/services/product_service.py",
        hunk_index=0,
        hunk=hunk,
        enclosing_entity=entity,
        relevant_imports=["from decimal import Decimal"],
        relevant_callers=["create_product", "api_v1_products"],
    )

    return pr_context, hunk_context


def run_smoke_test() -> int:
    print("=" * 70)
    print("  ChangeGuard: Gemini API Semantic Intent Smoke Test")
    print("=" * 70)

    effective_model = settings.get_effective_model_name()
    api_key = settings.get_gemini_api_key()

    print(f"Provider:             {settings.AI_PROVIDER}")
    print(f"Model ID:             {effective_model}")
    print(f"API Key Present:      {'YES (' + mask_key(api_key) + ')' if api_key else 'NO'}")
    print(f"Timeout:              {settings.AI_TIMEOUT_SECONDS}s")
    print(f"Max Output Tokens:    {settings.AI_MAX_OUTPUT_TOKENS}")
    print(f"Fallback Enabled:     {settings.AI_FALLBACK_ENABLED}")
    print(f"Cache Enabled:        {settings.AI_CACHE_ENABLED}")
    print("-" * 70)

    pr_ctx, hunk_ctx = build_synthetic_pr()
    engine = GeminiSemanticEngine(
        model_name=effective_model,
        api_key=api_key,
        timeout_seconds=settings.AI_TIMEOUT_SECONDS,
        fallback_enabled=settings.AI_FALLBACK_ENABLED,
    )

    print("Evaluating synthetic PR hunk against stated intent...")
    start_time = time.perf_counter()

    try:
        assessment = engine.assess_hunk(pr_ctx, hunk_ctx, similarity_score=0.45)
        duration = time.perf_counter() - start_time

        print(f"Request Completed In: {duration:.2f}s")
        print(f"Reported Provider:    {assessment.provider_type}")
        print(f"Classification:       {assessment.classification.value}")
        print(f"Confidence:           {assessment.confidence:.2f}")
        print(f"Uncertainty:          {assessment.uncertainty_level.value}")
        print(f"Apparent Purpose:     {assessment.apparent_purpose}")
        print(f"Reason:               {assessment.reason}")
        print(f"Evidence:             {assessment.evidence}")
        if assessment.contradiction_signals:
            print(f"Contradictions:       {assessment.contradiction_signals}")
        if assessment.missing_context:
            print(f"Disclosed Context:    {assessment.missing_context}")

        print("-" * 70)
        if "gemini_fallback" in assessment.provider_type:
            print("Status: COMPLETED VIA DETERMINISTIC FALLBACK")
            print("Notice: The live Gemini API call failed or was unconfigured, and ChangeGuard's")
            print("        deterministic fallback safely processed the request without failure.")
        else:
            print("Status: SUCCESS (LIVE GEMINI API INFERENCE VERIFIED)")
        print("=" * 70)
        return 0

    except Exception as exc:
        duration = time.perf_counter() - start_time
        print(f"Request FAILED in {duration:.2f}s: {redact_sensitive_tokens(str(exc))}")
        print("Status: FAILED (Fallback disabled or fatal exception)")
        print("=" * 70)
        return 1


if __name__ == "__main__":
    sys.exit(run_smoke_test())
