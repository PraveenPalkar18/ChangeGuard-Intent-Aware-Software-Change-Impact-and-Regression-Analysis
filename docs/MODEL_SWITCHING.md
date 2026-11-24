# ChangeGuard: Model Switching Guide

> **Objective**: Enable any developer to configure, switch, or extend AI model providers in ChangeGuard cleanly through configuration or modular code extensions.

---

## 1. Quick Switching via Configuration (No Code Changes)

ChangeGuard ships with four built-in model providers:
- `groq`: Ultra-fast cloud LPU inference using Meta Llama or Qwen models.
- `gemini`: Hosted Google GenAI LLM using `gemini-2.5-flash` or `gemini-3.8-flash`.
- `tfidf`: Local deterministic cosine similarity baseline with compound sub-token expansion (100% offline).
- `mock`: Deterministic token overlap for offline test suites.

### Step 1: Update `.env`
Edit your local `.env` file to select your desired provider:

```dotenv
# Option 1: Groq Cloud LPU (Recommended for production & fast review)
AI_PROVIDER=groq
GROQ_API_KEY=gsk_your_groq_api_key_here
AI_MODEL_NAME=llama-3.3-70b-versatile

# Option 2: Google Gemini (High reasoning multi-modal LLM)
# AI_PROVIDER=gemini
# GEMINI_API_KEY=your_gemini_api_key_here
# AI_MODEL_NAME=gemini-2.5-flash

# Option 3: Local Deterministic Baseline (Zero network, 100% privacy)
# AI_PROVIDER=tfidf
# AI_MODEL_NAME=tfidf-word-v1

# Option 4: Mock Provider (Testing)
# AI_PROVIDER=mock
# AI_MODEL_NAME=mock-jaccard

# Universal Fallback Setting (Recommended: true)
AI_FALLBACK_ENABLED=true
AI_TIMEOUT_SECONDS=30
```

### Step 2: Verify Provider Initialization
Run the automated test suite to confirm your configuration is working:
```powershell
pytest backend/tests/test_intent_analyzer.py -v
```

If using Groq:
```powershell
python scripts/groq_smoke_test.py
```

If using Gemini:
```powershell
python scripts/gemini_smoke_test.py
```

---

## 2. Adding a Completely New Model Provider

To integrate a new model (e.g. `ollama`, `anthropic`, `vllm`, or `custom-endpoint`):

### Step 1: Implement `AIModelProvider`
Create a new file in `backend/app/intent/providers/my_new_provider.py`:

```python
from typing import Dict, Any
from backend.app.intent.provider_interface import AIModelProvider

class CustomModelProvider(AIModelProvider):
    def __init__(self, model_name: str = "custom-model"):
        self._model_name = model_name

    @property
    def provider_name(self) -> str:
        return "custom"

    @property
    def model_name(self) -> str:
        return self._model_name

    def compute_similarity(self, text_a: str, text_b: str) -> float:
        """Calculate similarity between stated intent and code hunk.
        
        Returns float between 0.0 and 1.0.
        """
        if not text_a or not text_b:
            return 0.0
        # Custom inference logic
        return 0.85

    def get_model_info(self) -> Dict[str, Any]:
        return {
            "provider": self.provider_name,
            "model": self.model_name,
            "latency": "sub-second",
        }
```

### Step 2: Register in `backend/app/intent/factory.py`
Open `backend/app/intent/factory.py` and add your provider to `_instantiate_single_provider`:

```python
from backend.app.intent.providers.my_new_provider import CustomModelProvider

def _instantiate_single_provider(provider_key: str, model_name: Optional[str]) -> AIModelProvider:
    if provider_key == "custom":
        return CustomModelProvider(model_name=model_name or "custom-model")
    ...
```

### Step 3: Export in `backend/app/intent/providers/__init__.py`
Export your provider class in `backend/app/intent/providers/__init__.py`.

---

## 3. Expected Interface Contract

Every model provider must strictly adhere to `AIModelProvider` in `backend/app/intent/provider_interface.py`:

```python
class AIModelProvider(ABC):
    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Unique identifier (e.g. 'groq', 'gemini', 'tfidf')."""
        pass

    @property
    @abstractmethod
    def model_name(self) -> str:
        """Specific model ID (e.g. 'llama-3.3-70b-versatile')."""
        pass

    @abstractmethod
    def compute_similarity(self, text_a: str, text_b: str) -> float:
        """Must return float in [0.0, 1.0]. Zero when inputs are empty."""
        pass

    @abstractmethod
    def get_model_info(self) -> Dict[str, Any]:
        """Diagnostic metadata dictionary."""
        pass
```

---

## 4. Verification and Safety Checklist

Whenever adding or switching models:
1. **Empty Input Safety**: Confirm `compute_similarity("", "") == 0.0` without raising unhandled exceptions.
2. **Boundary Checks**: Confirm all similarity outputs stay strictly within `[0.0, 1.0]`.
3. **Secret Redaction**: Verify sensitive tokens (`ghp_...`, `gsk_...`, private keys) are scrubbed before cloud dispatch.
4. **Run Full Test Suite**:
   ```powershell
   pytest backend/tests/test_intent_analyzer.py
   ```
