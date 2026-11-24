"""ChangeGuard: Groq Free-Tier AI API Semantic Intent Checking Smoke Test.

Executes a minimal, real text-generation request to Groq using the official
groq Python SDK and verifies that the real Groq API responds with structured
intent classification.

Usage:
    python scripts/groq_smoke_test.py
"""
import os
import sys
import time

# Ensure project root is in sys.path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from dotenv import load_dotenv
load_dotenv(override=True)

from backend.app.core.config import settings
from backend.app.intent.models import PRContext, HunkContext
from backend.app.preprocessing.models import DiffHunk, DiffLine, DiffLineType
from backend.app.repository.models import CodeEntity, CodeEntityType
from backend.app.intent.semantic_engine import GroqSemanticEngine, redact_sensitive_tokens


def mask_key(key: str) -> str:
    """Masks an API key for safe display (e.g., gsk_...xxxx). Never prints full key."""
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
    print("  ChangeGuard: Groq Free-Tier API Semantic Intent Smoke Test")
    print("=" * 70)

    effective_model = settings.get_effective_model_name()
    if effective_model in ("gemini-3.8-flash", "tfidf-word-v1"):
        effective_model = "llama-3.3-70b-versatile"

    api_key = settings.get_groq_api_key()

    print(f"Configured Provider:  {settings.AI_PROVIDER}")
    print(f"Target Groq Model:    {effective_model}")
    print(f"API Key Present:      {'YES (' + mask_key(api_key) + ')' if api_key else 'NO'}")
    print(f"Timeout:              {settings.AI_TIMEOUT_SECONDS}s")
    print(f"Max Output Tokens:    {settings.AI_MAX_OUTPUT_TOKENS}")
    print("-" * 70)

    if not api_key:
        print("[BLOCKED] GROQ_API_KEY is not set in your environment or .env file.")
        print()
        print("To configure Groq Free Tier:")
        print("  1. Sign in to https://console.groq.com/ and create a free API key at:")
        print("     https://console.groq.com/keys")
        print("  2. Add the key to your .env file:")
        print("     AI_PROVIDER=groq")
        print("     GROQ_API_KEY=gsk_your_actual_key_here")
        print(f"     AI_MODEL_NAME={effective_model}")
        print("  3. Save the .env file (Ctrl+S) and re-run this script.")
        print("=" * 70)
        return 1

    pr_ctx, hunk_ctx = build_synthetic_pr()
    engine = GroqSemanticEngine(
        model_name=effective_model,
        api_key=api_key,
        timeout_seconds=settings.AI_TIMEOUT_SECONDS,
        max_output_tokens=settings.AI_MAX_OUTPUT_TOKENS,
        fallback_enabled=False,  # Enforce direct call to verify real Groq API
    )

    print(f"Sending real Groq API request to model '{effective_model}'...")
    start_time = time.perf_counter()

    try:
        assessment = engine.assess_hunk(pr_ctx, hunk_ctx, similarity_score=0.45)
        elapsed_ms = (time.perf_counter() - start_time) * 1000

        print(f"[SUCCESS] Real Groq API request completed in {elapsed_ms:.1f}ms")
        print("-" * 70)
        print(f"Provider Attribution: {assessment.provider_type}")
        print(f"Classification:       {assessment.classification.value}")
        print(f"Confidence:           {assessment.confidence:.2f}")
        print(f"Uncertainty:          {assessment.uncertainty_level.value}")
        print(f"Apparent Purpose:     {assessment.apparent_purpose}")
        print(f"Reason:               {assessment.reason}")
        if assessment.evidence:
            print("Evidence:")
            for ev in assessment.evidence:
                print(f"  - {ev}")
        print("=" * 70)
        return 0

    except Exception as exc:
        elapsed_ms = (time.perf_counter() - start_time) * 1000
        sanitized = redact_sensitive_tokens(str(exc))
        if api_key:
            sanitized = sanitized.replace(api_key, "[REDACTED_API_KEY]")
        print(f"[FAILURE] Real Groq API request failed after {elapsed_ms:.1f}ms")
        print(f"Error Details: {sanitized}")
        print("=" * 70)
        return 1


if __name__ == "__main__":
    sys.exit(run_smoke_test())
