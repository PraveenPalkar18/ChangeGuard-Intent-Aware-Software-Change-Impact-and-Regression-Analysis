"""Concrete Intent Analyzer evaluating PR intent against diff hunks."""
import re
from typing import List, Optional, Set
from backend.app.intent.analyzer_interface import BaseIntentAnalyzer
from backend.app.intent.provider_interface import AIModelProvider
from backend.app.intent.factory import create_model_provider
from backend.app.intent.models import (
    PRContext,
    HunkContext,
    HunkIntentResult,
    IntentClassification,
    PRIntentReport,
)


class IntentAnalyzer(BaseIntentAnalyzer):
    """Orchestrates hunk-level intent classification with semantic and heuristic guards."""

    def __init__(
        self,
        provider: Optional[AIModelProvider] = None,
        explained_threshold: float = 0.20,
        unexplained_threshold: float = 0.05,
    ):
        self._provider = provider or create_model_provider()
        self._explained_threshold = explained_threshold
        self._unexplained_threshold = unexplained_threshold

    @property
    def provider(self) -> AIModelProvider:
        return self._provider

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
                evidence=["Stated PR description and title are empty or absent."],
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
                evidence=["Empty diff hunk patch."],
                limitations=limitations,
                model_used=self._provider.model_name,
                provider_used=self._provider.provider_name,
            )

        # 3. Direct Symbol / Entity Mention Heuristic
        entity_name = hunk_context.enclosing_entity.name if hunk_context.enclosing_entity else None
        file_stem = hunk_context.file_path.split("/")[-1].split(".")[0]
        intent_lower = intent_text.lower()

        direct_entity_match = False
        if entity_name and len(entity_name) > 2 and entity_name.lower() in intent_lower:
            direct_entity_match = True
            evidence.append(f"Entity '{entity_name}' is explicitly referenced in the PR intent text.")

        if file_stem and len(file_stem) > 2 and file_stem.lower() in intent_lower:
            evidence.append(f"Filename/module '{file_stem}' is explicitly referenced in the PR intent text.")

        # 4. Compute Semantic/Lexical Similarity Score
        similarity = self._provider.compute_similarity(intent_text, code_text)
        evidence.append(f"Model similarity score: {similarity:.4f} (thresholds: explained >= {self._explained_threshold}, unexplained < {self._unexplained_threshold})")

        # 5. Test File / Supporting Artifact Heuristic
        is_test_file = "test" in hunk_context.file_path.lower()
        if is_test_file:
            evidence.append("Target file is a test suite component supporting implementation changes.")

        # 6. Classification Decision Logic
        if direct_entity_match or similarity >= self._explained_threshold:
            classification = IntentClassification.EXPLAINED
            confidence = min(0.95, round(0.65 + 0.35 * similarity, 2))
            reason = f"Change in '{hunk_context.file_path}' shows strong semantic alignment with the stated PR intent."
            if direct_entity_match:
                reason += f" Direct reference to symbol '{entity_name}' confirmed."

        elif is_test_file and similarity >= self._unexplained_threshold:
            classification = IntentClassification.EXPLAINED
            confidence = 0.70
            reason = f"Test suite change in '{hunk_context.file_path}' aligns as a supporting regression test for PR modifications."

        elif similarity < self._unexplained_threshold and not direct_entity_match and not is_test_file:
            # Low similarity without any linking heuristics
            classification = IntentClassification.UNEXPLAINED
            confidence = min(0.85, round(0.70 + (self._unexplained_threshold - similarity), 2))
            reason = f"No meaningful semantic overlap or symbol references connect the changes in '{hunk_context.file_path}' with the stated PR intent."
            limitations.append("A legitimate cross-cutting refactor or secondary dependency modification may trigger an unconfirmed UNEXPLAINED flag.")

        else:
            # Intermediate range or ambiguous case -> UNCERTAIN
            classification = IntentClassification.UNCERTAIN
            confidence = 0.55
            reason = f"Partial or inconclusive semantic alignment ({similarity:.2f}) between change in '{hunk_context.file_path}' and stated PR intent."

        return HunkIntentResult(
            hunk_index=hunk_context.hunk_index,
            file_path=hunk_context.file_path,
            classification=classification,
            confidence=confidence,
            similarity_score=similarity,
            reason=reason,
            evidence=evidence,
            limitations=limitations,
            model_used=self._provider.model_name,
            provider_used=self._provider.provider_name,
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
        uncertain = 0

        for hunk_ctx in hunk_contexts:
            res = self.analyze_hunk(pr_context, hunk_ctx)
            results.append(res)
            if res.classification == IntentClassification.EXPLAINED:
                explained += 1
            elif res.classification == IntentClassification.UNEXPLAINED:
                unexplained += 1
            else:
                uncertain += 1

        total = len(results)
        if total == 0:
            summary = "No code hunks found to analyze."
        elif unexplained == 0 and uncertain == 0:
            summary = f"All {total} hunks are explained by the stated PR intent."
        elif unexplained > 0:
            summary = f"Caution: {unexplained} of {total} hunks have unexplained modifications that may not align with stated PR intent."
        else:
            summary = f"{explained} hunks explained, {uncertain} hunks require reviewer confirmation due to ambiguous or cross-component overlap."

        return PRIntentReport(
            pr_number=pr_number if pr_number > 0 else None,
            total_hunks=total,
            explained_count=explained,
            unexplained_count=unexplained,
            uncertain_count=uncertain,
            hunk_results=results,
            summary=summary,
        )
