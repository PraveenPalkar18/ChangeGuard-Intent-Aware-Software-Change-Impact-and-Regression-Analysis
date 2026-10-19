"""Pretrained CodeBERT / UniXcoder similarity provider implementation."""
import os
from typing import Dict, Any, Optional
from backend.app.intent.provider_interface import AIModelProvider
from backend.app.core.exceptions import ChangeGuardException


class ModelNotAvailableException(ChangeGuardException):
    """Raised when an optional transformer model or runtime library is not available."""
    def __init__(self, message: str, details: Optional[dict] = None):
        super().__init__(message=message, status_code=503, details=details)


class CodeBERTSimilarityProvider(AIModelProvider):
    """Semantic code similarity provider using pretrained CodeBERT (or UniXcoder)."""

    def __init__(self, model_name: str = "microsoft/codebert-base", device: str = "cpu"):
        self._model_name = model_name
        self._device = device
        self._model = None
        self._tokenizer = None
        self._is_initialized = False
        self._init_error = None

    @property
    def provider_name(self) -> str:
        return "codebert"

    @property
    def model_name(self) -> str:
        return self._model_name

    def _ensure_initialized(self):
        """Lazy loader for torch and transformers dependencies."""
        if self._is_initialized:
            return

        try:
            import torch
            from transformers import AutoTokenizer, AutoModel

            self._tokenizer = AutoTokenizer.from_pretrained(self._model_name)
            self._model = AutoModel.from_pretrained(self._model_name).to(self._device)
            self._model.eval()
            self._is_initialized = True
        except ImportError as exc:
            self._init_error = f"Missing dependency for CodeBERT: {str(exc)}. Install 'torch' and 'transformers'."
            raise ModelNotAvailableException(self._init_error)
        except Exception as exc:
            self._init_error = f"Failed to load checkpoint '{self._model_name}': {str(exc)}"
            raise ModelNotAvailableException(self._init_error)

    def compute_similarity(self, text_a: str, text_b: str) -> float:
        """Compute cosine similarity between CodeBERT contextual embeddings."""
        if not text_a or not text_b or not text_a.strip() or not text_b.strip():
            return 0.0

        self._ensure_initialized()

        import torch
        import torch.nn.functional as F

        # Tokenize and encode texts with truncation
        inputs_a = self._tokenizer(text_a, return_tensors="pt", max_length=512, truncation=True, padding=True).to(self._device)
        inputs_b = self._tokenizer(text_b, return_tensors="pt", max_length=512, truncation=True, padding=True).to(self._device)

        with torch.no_grad():
            outputs_a = self._model(**inputs_a)
            outputs_b = self._model(**inputs_b)

            # Mean pooling over attention mask
            mask_a = inputs_a["attention_mask"].unsqueeze(-1)
            emb_a = (outputs_a.last_hidden_state * mask_a).sum(dim=1) / mask_a.sum(dim=1)

            mask_b = inputs_b["attention_mask"].unsqueeze(-1)
            emb_b = (outputs_b.last_hidden_state * mask_b).sum(dim=1) / mask_b.sum(dim=1)

            cosine_sim = F.cosine_similarity(emb_a, emb_b).item()

        # Clamp between 0.0 and 1.0
        normalized = max(0.0, min(1.0, float(cosine_sim)))
        return round(normalized, 4)

    def get_model_info(self) -> Dict[str, Any]:
        return {
            "provider": self.provider_name,
            "model": self.model_name,
            "type": "pretrained-transformer",
            "device": self._device,
            "is_initialized": self._is_initialized,
            "init_error": self._init_error,
            "context_window": "512 tokens",
            "hardware_requirements": "8GB RAM minimum, CUDA GPU recommended for fast inference",
            "approximate_cost": "Local inference (0.00)",
            "limitations": [
                "512 token truncation window limits large hunks",
                "Higher latency compared to TF-IDF baseline on CPU",
                "Requires downloading ~500MB weights from Hugging Face",
            ],
        }
