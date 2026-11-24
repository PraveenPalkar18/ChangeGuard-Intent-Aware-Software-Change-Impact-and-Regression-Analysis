"""Concrete Intent Analyzer evaluating PR intent against diff hunks."""
import re
from typing import List, Optional, Set
from backend.app.intent.analyzer_interface import BaseIntentAnalyzer
from backend.app.intent.provider_interface import AIModelProvider
from backend.app.intent.factory import create_model_provider
from backend.app.intent.semantic_engine import (
    BaseSemanticEngine,
    create_semantic_engine,
    _global_semantic_cache,
)
from backend.app.intent.models import (
    PRContext,
    HunkContext,
    HunkIntentResult,
    IntentClassification,
    PRIntentReport,
    UncertaintyLevel,
)


class IntentAnalyzer(BaseIntentAnalyzer):
    """Orchestrates hunk-level intent classification with semantic and heuristic guards."""

    def __init__(
        self,
        provider: Optional[AIModelProvider] = None,
        semantic_engine: Optional[BaseSemanticEngine] = None,
        provider_name: Optional[str] = None,
        model_name: Optional[str] = None,
        explained_threshold: float = 0.20,
        unexplained_threshold: float = 0.05,
    ):
        if provider is not None:
            self._provider = provider
        else:
            self._provider = create_model_provider(provider_name=provider_name, model_name=model_name)

        if semantic_engine is not None:
            self._semantic_engine = semantic_engine
        else:
            self._semantic_engine = create_semantic_engine(provider_name=provider_name, model_name=model_name)

        self._explained_threshold = explained_threshold
        self._unexplained_threshold = unexplained_threshold

    @property
    def provider(self) -> AIModelProvider:
        return self._provider

    @property
    def semantic_engine(self) -> BaseSemanticEngine:
        return self._semantic_engine

    def analyze_hunk(self, pr_context: PRContext, hunk_context: HunkContext) -> HunkIntentResult:
        """Evaluate whether a diff hunk aligns with stated PR intent."""
        intent_text = pr_context.full_intent_text
        code_text = hunk_context.code_representation

        evidence: List[str] = []
        limitations: List[str] = [
            "Semantic similarity alone does not constitute mathematical proof of intent alignment.",
            "Static analysis cannot detect dynamic runtime or indirect call linkages.",
        ]

        # 1. Edge Case: Empty or missing PR description and title
        if not intent_text or not intent_text.strip():
            return HunkIntentResult(
                hunk_index=hunk_context.hunk_index,
                file_path=hunk_context.file_path,
                classification=IntentClassification.UNCERTAIN,
                confidence=0.50,
                similarity_score=0.0,
                reason="Pull Request intent is empty or missing; cannot verify whether this change was intended.",
                apparent_purpose="Unknown code modification",
                evidence=["Stated PR description and title are empty or absent."],
                contradiction_signals=[],
                missing_context=["PR title and description are missing."],
                uncertainty_score=0.90,
                semantic_assessment=None,
                limitations=limitations,
                model_used=self._provider.model_name,
                provider_used=self._provider.provider_name,
            )

        # 2. Edge Case: Empty hunk code
        if not code_text or not code_text.strip():
            return HunkIntentResult(
                hunk_index=hunk_context.hunk_index,
                file_path=hunk_context.file_path,
                classification=IntentClassification.UNCERTAIN,
                confidence=0.50,
                similarity_score=0.0,
                reason="Hunk contains no inspectable code lines or metadata.",
                apparent_purpose="Empty hunk",
                evidence=["Empty diff hunk patch."],
                contradiction_signals=[],
                missing_context=["No executable lines in diff hunk."],
                uncertainty_score=0.90,
                semantic_assessment=None,
                limitations=limitations,
                model_used=self._provider.model_name,
                provider_used=self._provider.provider_name,
            )

        # 3. Compute Deterministic Algorithmic Similarity Score (TF-IDF Baseline)
        similarity = self._provider.compute_similarity(intent_text, code_text)
        evidence.append(
            f"Algorithmic TF-IDF similarity score: {similarity:.4f} "
            f"(thresholds: explained >= {self._explained_threshold}, unexplained < {self._unexplained_threshold})"
        )

        # 4. Check Semantic Cache
        cached_assessment = _global_semantic_cache.get(
            pr_context=pr_context,
            hunk_context=hunk_context,
            provider_name=self._semantic_engine.provider_type,
            model_name=self._semantic_engine.model_name,
        )

        if cached_assessment is not None:
            semantic_assessment = cached_assessment
        else:
            # 5. Modular Semantic Assessment Layer
            semantic_assessment = self._semantic_engine.assess_hunk(
                pr_context=pr_context,
                hunk_context=hunk_context,
                similarity_score=similarity,
            )
            _global_semantic_cache.set(
                pr_context=pr_context,
                hunk_context=hunk_context,
                provider_name=self._semantic_engine.provider_type,
                model_name=self._semantic_engine.model_name,
                assessment=semantic_assessment,
            )

        # 6. Aggregate Evidence from Semantic Layer
        if semantic_assessment.evidence:
            for ev in semantic_assessment.evidence:
                if ev not in evidence:
                    evidence.append(ev)

        # 7. Final Classification Decision
        # Priority: Contradiction > Semantic Assessment > Fallback similarity
        classification = semantic_assessment.classification
        confidence = semantic_assessment.confidence
        reason = semantic_assessment.reason

        uncertainty_val = 0.20
        if semantic_assessment.uncertainty_level == UncertaintyLevel.HIGH:
            uncertainty_val = 0.80
        elif semantic_assessment.uncertainty_level == UncertaintyLevel.MEDIUM:
            uncertainty_val = 0.50

        # Construct combined provider label
        if any(self._semantic_engine.provider_type.startswith(p) for p in ("llm", "gemini", "groq")):
            provider_label = f"{self._provider.provider_name} + {self._semantic_engine.provider_type}"
        else:
            provider_label = self._provider.provider_name


        return HunkIntentResult(
            hunk_index=hunk_context.hunk_index,
            file_path=hunk_context.file_path,
            classification=classification,
            confidence=confidence,
            similarity_score=similarity,
            reason=reason,
            apparent_purpose=semantic_assessment.apparent_purpose,
            evidence=evidence,
            contradiction_signals=semantic_assessment.contradiction_signals,
            missing_context=semantic_assessment.missing_context,
            uncertainty_score=uncertainty_val,
            semantic_assessment=semantic_assessment,
            limitations=limitations,
            model_used=self._provider.model_name,
            provider_used=provider_label,
            raw_details={
                "tfidf_similarity": similarity,
                "semantic_provider": self._semantic_engine.provider_type,
                "semantic_model": self._semantic_engine.model_name,
            },
        )

    def analyze_pull_request(
        self,
        pr_context: PRContext,
        hunk_contexts: List[HunkContext],
        pr_number: int = 0,
    ) -> PRIntentReport:
        """Analyze all diff hunks in a PR and build aggregate report."""
        results: List[HunkIntentResult] = []
        explained = 0
        unexplained = 0
        contradictory = 0
        uncertain = 0

        for hunk_ctx in hunk_contexts:
            res = self.analyze_hunk(pr_context, hunk_ctx)
            results.append(res)
            if res.classification == IntentClassification.EXPLAINED:
                explained += 1
            elif res.classification == IntentClassification.UNEXPLAINED:
                unexplained += 1
            elif res.classification == IntentClassification.CONTRADICTORY:
                contradictory += 1
            else:
                uncertain += 1

        total = len(results)
        if total == 0:
            summary = "No code hunks found to analyze."
        elif contradictory > 0:
            summary = (
                f"Warning: {contradictory} of {total} hunks show direct contradictions or scope divergence "
                f"with stated PR intent. Reviewer verification required."
            )
        elif unexplained == 0 and uncertain == 0:
            summary = f"All {total} hunks are explained by the stated PR intent."
        elif unexplained > 0:
            summary = f"Attention: {unexplained} of {total} hunks contain unexplained modifications that do not align with stated PR intent."
        else:
            summary = f"{explained} hunks explained, {uncertain} hunks require reviewer confirmation due to ambiguous or cross-component overlap."

        return PRIntentReport(
            pr_number=pr_number if pr_number > 0 else None,
            total_hunks=total,
            explained_count=explained,
            unexplained_count=unexplained,
            contradictory_count=contradictory,
            uncertain_count=uncertain,
            hunk_results=results,
            summary=summary,
        )
