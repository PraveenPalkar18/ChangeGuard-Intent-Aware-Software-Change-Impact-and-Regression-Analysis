"""TF-IDF Lexical Similarity Provider."""
import math
import re
from typing import Dict, Any, List, Set
from collections import Counter
from backend.app.intent.provider_interface import AIModelProvider


class TFIDFSimilarityProvider(AIModelProvider):
    """Computes TF-IDF cosine similarity between intent descriptions and code hunks."""

    def __init__(self, model_name: str = "tfidf-word-v1"):
        self._model_name = model_name
        self._sklearn_available = self._check_sklearn()

    def _check_sklearn(self) -> bool:
        try:
            import sklearn
            return True
        except ImportError:
            return False

    @property
    def provider_name(self) -> str:
        return "tfidf"

    @property
    def model_name(self) -> str:
        return self._model_name

    def _preprocess_code_text(self, text: str) -> str:
        """Expand compound identifiers (camelCase, snake_case) to bridge code and intent vocabulary."""
        if not text:
            return ""
        # Split camelCase e.g. calculateDiscount -> calculate Discount
        s = re.sub(r"([a-z])([A-Z])", r"\1 \2", text)
        # Split snake_case and preserve parts: calculate_discount -> calculate discount calculate_discount
        tokens = s.split()
        expanded = []
        for token in tokens:
            expanded.append(token)
            if "_" in token:
                parts = token.split("_")
                expanded.extend([p for p in parts if p])
        return " ".join(expanded)

    def compute_similarity(self, text_a: str, text_b: str) -> float:
        """Compute cosine similarity using TF-IDF representation."""
        if not text_a or not text_b or not text_a.strip() or not text_b.strip():
            return 0.0

        proc_a = self._preprocess_code_text(text_a)
        proc_b = self._preprocess_code_text(text_b)

        if self._sklearn_available:
            try:
                return self._compute_sklearn_similarity(proc_a, proc_b)
            except Exception:
                return self._compute_native_similarity(proc_a, proc_b)
        else:
            return self._compute_native_similarity(proc_a, proc_b)

    def _compute_sklearn_similarity(self, text_a: str, text_b: str) -> float:
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.metrics.pairwise import cosine_similarity

        vectorizer = TfidfVectorizer(
            ngram_range=(1, 1),
            token_pattern=r"(?u)\b[a-zA-Z_][a-zA-Z0-9_]*\b",
            sublinear_tf=True,
            stop_words="english",
        )
        try:
            tfidf_matrix = vectorizer.fit_transform([text_a, text_b])
            sim = cosine_similarity(tfidf_matrix[0:1], tfidf_matrix[1:2])[0][0]
            return round(float(sim), 4)
        except ValueError:
            return 0.0

    def _compute_native_similarity(self, text_a: str, text_b: str) -> float:
        """Deterministic pure-Python TF-IDF implementation as zero-dependency fallback."""
        tokens_a = self._tokenize(text_a)
        tokens_b = self._tokenize(text_b)

        if not tokens_a or not tokens_b:
            return 0.0

        docs = [tokens_a, tokens_b]
        vocab = set(tokens_a).union(set(tokens_b))

        # Document frequencies
        df = {term: sum(1 for d in docs if term in d) for term in vocab}
        num_docs = len(docs)

        # Compute TF-IDF vectors
        def get_tfidf_vec(doc_tokens: List[str]) -> Dict[str, float]:
            tf = Counter(doc_tokens)
            vec = {}
            for term, count in tf.items():
                tf_val = 1.0 + math.log(count)
                idf_val = math.log((num_docs + 1) / (df.get(term, 0) + 1)) + 1.0
                vec[term] = tf_val * idf_val
            # Normalize vector
            norm = math.sqrt(sum(v ** 2 for v in vec.values()))
            if norm == 0:
                return {}
            return {k: v / norm for k, v in vec.items()}

        vec_a = get_tfidf_vec(tokens_a)
        vec_b = get_tfidf_vec(tokens_b)

        # Dot product
        common = set(vec_a.keys()).intersection(set(vec_b.keys()))
        score = sum(vec_a[t] * vec_b[t] for t in common)
        return round(float(score), 4)

    def _tokenize(self, text: str) -> List[str]:
        words = re.findall(r"\b[a-zA-Z_][a-zA-Z0-9_]+\b", text.lower())
        stops = {
            "the", "a", "an", "and", "or", "in", "on", "of", "to", "for", "is",
            "it", "this", "that", "with", "as", "by", "from", "at", "be", "was",
        }
        return [w for w in words if len(w) > 1 and w not in stops]

    def get_model_info(self) -> Dict[str, Any]:
        return {
            "provider": self.provider_name,
            "model": self.model_name,
            "backend": "scikit-learn" if self._sklearn_available else "pure-python",
            "hardware_requirements": "CPU only (low memory)",
            "approximate_cost": "0.00",
            "context_window": "unlimited",
            "limitations": [
                "Does not generalize to semantic synonyms (e.g. 'remove' vs 'delete')",
                "Vulnerable to vocabulary mismatch between natural language intent and code symbols",
            ],
        }
